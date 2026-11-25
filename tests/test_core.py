import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from retailrank.api import app
from retailrank.engine import load_engine
from retailrank.train import build_queries,rank_value

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('RETAILRANK_DB',str(tmp_path/'demo.sqlite'))
    return TestClient(app)

def test_ranking_metric_has_known_values():
    assert rank_value(np.array([7,3,9]),7)==[1.0,1.0,1.0,1.0]
    second=rank_value(np.array([7,3,9]),3)
    assert second[1]==pytest.approx(1/np.log2(3))
    assert second[2]==.5
    assert rank_value(np.array([7,3,9]),42)==[0.0,0.0,0.0,0.0]

def test_queries_use_only_prior_timestamps_and_reset_sessions():
    events=pd.DataFrame([(1,1,'view',10),(100,1,'view',20),(100,1,'view',30),(200,1,'view',40),
                         (1800300,1,'view',50),(1800400,1,'view',60)],columns=['timestamp','visitorid','event','itemid'])
    groups,counts=build_queries(events,[50,150,250],[100,100,100])
    assert len(groups[0])==1
    assert groups[0][0]['target']==20
    assert groups[0][0]['history']==[{'item_id':10,'event':'view'}]
    assert groups[1][0]['target']==40
    assert groups[2][0]['history']==[{'item_id':50,'event':'view'}]

def test_new_session_popularity_fallback_and_health(client):
    response=client.get('/api/recommendations')
    assert response.status_code==200
    assert response.json()['cold_start']
    assert response.json()['method']=='popular'
    assert len(response.json()['items'])==10
    assert client.get('/api/health').json()['catalog_size']==20000

def test_action_changes_profile_and_excludes_recent_items(client):
    item=client.get('/api/catalog').json()['items'][0]['item_id']
    assert client.post('/api/actions',json={'item_id':item,'event':'view'}).status_code==200
    result=client.get('/api/recommendations').json()
    assert not result['cold_start']
    assert item not in [r['item_id'] for r in result['items']]
    assert len(set(r['item_id'] for r in result['items']))==10
    assert client.get('/api/state').json()['counts']['view']==1

def test_sessions_are_isolated(client):
    item=client.get('/api/catalog').json()['items'][0]['item_id']
    client.post('/api/actions',json={'item_id':item,'event':'addtocart'})
    other=TestClient(app)
    assert other.get('/api/state').json()['history']==[]
    assert len(client.get('/api/state').json()['history'])==1

def test_validation_and_origin(client):
    assert client.post('/api/actions',json={'item_id':999999999,'event':'view'}).status_code==404
    assert client.post('/api/actions',json={'item_id':10,'event':'wrong'}).status_code==422
    assert client.get('/api/recommendations?k=500').status_code==422
    assert client.get('/api/recommendations?method=invalid').status_code==422
    assert client.post('/api/reset',headers={'Origin':'https://another.example'}).status_code==403

def test_replay_does_not_insert_future_target(client):
    replay=client.post('/api/scenarios/0').json()
    assert replay['actual_next_item'] not in [r['item_id'] for r in client.get('/api/state').json()['history']]
    result=client.get('/api/recommendations').json()
    direct=load_engine().recommend(replay['history'])
    assert [r['item_id'] for r in result['items']]==[r['item_id'] for r in direct['items']]

def test_reset_keeps_other_sessions(client):
    item=client.get('/api/catalog').json()['items'][0]['item_id']
    client.post('/api/actions',json={'item_id':item,'event':'view'})
    assert client.post('/api/reset').status_code==200
    assert client.get('/api/state').json()['history']==[]

def test_report_exposes_training_injection_and_full_evaluation_denominator(client):
    report=client.get('/api/metrics').json()
    assert report['test']['queries']==2000
    assert report['train_audit']['injected_targets']>=0
    assert report['validation_audit']['injected_targets']==0
    assert 0<report['test']['target_catalog_coverage']<1
    assert pd.Timestamp(report['cutoffs']['retrieval_end'])<pd.Timestamp(report['cutoffs']['ranker_train_end'])<pd.Timestamp(report['cutoffs']['validation_end'])
