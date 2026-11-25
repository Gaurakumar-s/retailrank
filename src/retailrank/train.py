"""Train an ALS retrieval + LambdaMART ranking system on chronological Retailrocket data."""
from collections import deque
from pathlib import Path
import argparse, hashlib, json, platform, time
import joblib
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix,csr_matrix
from implicit.als import AlternatingLeastSquares
import lightgbm as lgb
from .engine import Engine,ROOT,FEATURES,WEIGHTS

SEED=42

def log(**items):print(json.dumps(items),flush=True)
def date(ms):return pd.to_datetime(ms,unit='ms',utc=True).isoformat()

def build_queries(events,bounds,limits):
    """Reservoir samples of novel-within-recent-history transitions, at most 3 per session."""
    rng=np.random.default_rng(SEED)
    reservoirs=[[],[],[]]; counts=[0,0,0]
    data=events.sort_values(['visitorid','timestamp'],kind='stable')
    last_user=None;last_time=0;history=deque(maxlen=20);session_queries=0
    for timestamp,user,event,item in data[['timestamp','visitorid','event','itemid']].itertuples(index=False,name=None):
        if user!=last_user or timestamp-last_time>30*60*1000:
            history.clear();session_queries=0
        stage=int(np.searchsorted(bounds,timestamp,side='right'))-1
        if 0<=stage<3 and history and timestamp>last_time and item not in {x['item_id'] for x in history} and session_queries<3:
            query={'timestamp':int(timestamp),'history':list(history),'target':int(item),'target_event':event}
            counts[stage]+=1;session_queries+=1
            if len(reservoirs[stage])<limits[stage]:reservoirs[stage].append(query)
            else:
                index=int(rng.integers(counts[stage]))
                if index<limits[stage]:reservoirs[stage][index]=query
        history.append({'item_id':int(item),'event':event})
        last_user=user;last_time=timestamp
    return [sorted(rows,key=lambda r:r['timestamp']) for rows in reservoirs],counts

def fit_retriever(events,cutoff,catalog_size):
    past=events[events.timestamp<cutoff]
    popularity=past.itemid.value_counts()
    ids=popularity[popularity>=5].head(catalog_size).index.to_numpy(dtype=np.int64)
    mapping={int(v):i for i,v in enumerate(ids)}
    selected=past[past.itemid.isin(ids)].copy()
    sizes=selected.groupby('visitorid').itemid.nunique()
    # Exclude extremely long histories from factor fitting to limit bot-like influence.
    users=sizes[(sizes>=2)&(sizes<=100)].index
    selected=selected[selected.visitorid.isin(users)]
    user_ids,user_inverse=np.unique(selected.visitorid.to_numpy(),return_inverse=True)
    item_index=selected.itemid.map(mapping).to_numpy()
    values=selected.event.map(WEIGHTS).to_numpy(dtype=np.float32)
    matrix=coo_matrix((values,(user_inverse,item_index)),shape=(len(user_ids),len(ids))).tocsr()
    matrix.data=(1+15*np.log1p(matrix.data)).astype(np.float32)
    als=AlternatingLeastSquares(factors=32,regularization=.1,iterations=15,random_state=SEED,num_threads=2,use_gpu=False)
    als.fit(matrix,show_progress=False)
    types=pd.crosstab(past.itemid,past.event).reindex(ids,fill_value=0)
    views=types.get('view',pd.Series(0,index=types.index)).to_numpy()
    carts=types.get('addtocart',pd.Series(0,index=types.index)).to_numpy()
    buys=types.get('transaction',pd.Series(0,index=types.index)).to_numpy()
    counts=popularity.reindex(ids).to_numpy()
    recent=past[past.timestamp>=cutoff-7*86400000].itemid.value_counts().reindex(ids,fill_value=0).to_numpy()
    stats=np.column_stack([counts,(carts+1)/(views+20),(buys+1)/(views+20),recent/np.maximum(counts,1)])
    bundle={'item_ids':ids,'item_factors':als.item_factors,'item_stats':stats,'regularization':.1,
            'ranker':None,'model_version':'retailrank-v1','retrieval_cutoff':date(cutoff)}
    engine=Engine(bundle)
    # Cross-check online fold-in against the library's exact recalculation on the same history.
    example=[{'item_id':int(ids[0]),'event':'view'},{'item_id':int(ids[1]),'event':'addtocart'}]
    row=csr_matrix(([1+15*np.log1p(1),1+15*np.log1p(3)],([0,0],[0,1])),shape=(1,len(ids)),dtype=np.float32)
    expected=als.recalculate_user(0,row)@als.item_factors.T
    observed=engine.context(example)[0]
    parity=float(np.max(np.abs(expected-observed)))
    if not np.allclose(expected,observed,atol=1e-4,rtol=1e-3):raise AssertionError('Fold-in parity failed')
    return bundle,{'events_before_cutoff':len(past),'catalog_size':len(ids),'fitted_users':len(user_ids),
                   'fitted_events':len(selected),'user_filter':'2 to 100 distinct catalog items before cutoff',
                   'fold_in_max_score_difference':parity}

def training_rows(engine,queries,inject):
    xs=[];ys=[];groups=[];hits=0;eligible=0;unknown=0;profiles=0
    for q in queries:
        target=engine.lookup.get(q['target'])
        ids,als,similar,encoded=engine.candidates(q['history'])
        if target is None:unknown+=1;continue
        if not encoded:profiles+=1;continue
        eligible+=1;hit=target in ids;hits+=int(hit)
        if inject and not hit:ids=np.append(ids,target)
        x=engine.features(ids,als,similar,encoded)
        xs.append(x);ys.append((ids==target).astype(int));groups.append(len(ids))
    if not xs:raise ValueError('No eligible ranking queries')
    return np.vstack(xs),np.concatenate(ys),groups,{'eligible_queries':eligible,'retrieved_targets':hits,
        'injected_targets':eligible-hits if inject else 0,'unknown_catalog_targets':unknown,'unknown_profiles':profiles}

def rank_value(recommendations,target):
    matches=np.flatnonzero(recommendations==target)
    rank=int(matches[0])+1 if len(matches) else 0
    return [float(0<rank<=10),1/np.log2(rank+1) if 0<rank<=10 else 0.0,
            1/rank if 0<rank<=10 else 0.0,float(0<rank<=20)]

def evaluate(engine,queries):
    methods=['popular','als','similarity','ranker']
    rows={m:[] for m in methods};recommended={m:set() for m in methods};coverage=0;candidate_hits=0;profile_count=0
    example=[];latency=[]
    for index,q in enumerate(queries):
        target=engine.lookup.get(q['target'],-1)
        ids,als,similar,encoded=engine.candidates(q['history'])
        excluded=set(i for i,w in encoded)
        coverage+=target>=0;profile_count+=bool(encoded);candidate_hits+=target in ids
        predictions={'popular':np.array([i for i in engine.popular if i not in excluded][:20]),
                     'als':engine.top(als,20,excluded) if encoded else engine.popular[:20],
                     'similarity':engine.top(similar,20,excluded) if encoded else engine.popular[:20]}
        if encoded:
            scores=engine.ranker.booster_.predict(engine.features(ids,als,similar,encoded),num_threads=2)
            predictions['ranker']=ids[np.lexsort((ids,-scores))[:20]]
        else:predictions['ranker']=engine.popular[:20]
        for method,items in predictions.items():
            rows[method].append(rank_value(items,target));recommended[method].update(int(i) for i in items)
        if index<100:
            begin=time.perf_counter();engine.recommend(q['history']);latency.append((time.perf_counter()-begin)*1000)
        if len(example)<10 and encoded:
            example.append({'history':q['history'],'target':q['target'],'target_event':q['target_event'],
                            'timestamp':date(q['timestamp'])})
    results={}
    for m in methods:
        values=np.mean(rows[m],axis=0)
        results[m]=dict(zip(['hit_rate_at_10','ndcg_at_10','mrr_at_10','hit_rate_at_20'],map(float,values)))
        results[m]['catalog_coverage_at_20']=len(recommended[m])/len(engine.ids)
    # Paired bootstrap descriptive uncertainty; do not use test results to tune the model.
    delta=np.array(rows['ranker'])[:,1]-np.array(rows['als'])[:,1]
    rng=np.random.default_rng(SEED)
    means=[float(rng.choice(delta,len(delta),replace=True).mean()) for _ in range(1000)]
    return {'queries':len(queries),'methods':results,'candidate_recall':candidate_hits/len(queries),
            'target_catalog_coverage':coverage/len(queries),'known_profile_fraction':profile_count/len(queries),
            'ndcg_delta_vs_als_95pct_interval':list(map(float,np.percentile(means,[2.5,97.5]))),
            'local_latency_ms':{'p50':float(np.percentile(latency,50)),'p95':float(np.percentile(latency,95)),'samples':len(latency)},
            'examples':example}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--events',required=True);parser.add_argument('--catalog-size',type=int,default=20000)
    parser.add_argument('--train-queries',type=int,default=7000);parser.add_argument('--eval-queries',type=int,default=2000)
    args=parser.parse_args();begin=time.time()
    path=Path(args.events);events=pd.read_csv(path,usecols=['timestamp','visitorid','event','itemid'])
    original=len(events);events=events.drop_duplicates(['timestamp','visitorid','event','itemid'])
    start,end=int(events.timestamp.min()),int(events.timestamp.max())
    bounds=[int(start+(end-start)*f) for f in [.60,.75,.85]]
    log(stage='data',events=len(events),cutoffs=list(map(date,bounds)))
    bundle,retrieval=fit_retriever(events,bounds[0],args.catalog_size);engine=Engine(bundle)
    log(stage='retrieval_ready',**retrieval)
    sets,counts=build_queries(events,bounds,[args.train_queries,args.eval_queries,args.eval_queries])
    train,valid,test=sets
    log(stage='queries',available=counts,sampled=list(map(len,sets)))
    x,y,groups,train_audit=training_rows(engine,train,True)
    vx,vy,vgroups,val_audit=training_rows(engine,valid,False)
    log(stage='ranker_fit',rows=len(y),train_audit=train_audit,validation_audit=val_audit)
    ranker=lgb.LGBMRanker(objective='lambdarank',n_estimators=250,learning_rate=.05,num_leaves=15,
        min_child_samples=40,reg_lambda=2,random_state=SEED,n_jobs=2,verbosity=-1,deterministic=True,force_col_wise=True)
    ranker.fit(x,y,group=groups,eval_set=[(vx,vy)],eval_group=[vgroups],eval_at=[10],
        feature_name=FEATURES,callbacks=[lgb.early_stopping(25,verbose=False)])
    bundle['ranker']=ranker;engine=Engine(bundle)
    validation=evaluate(engine,valid);validation.pop('examples',None)
    log(stage='validation',methods=validation['methods'])
    # Test is evaluated exactly once after training and early stopping on validation.
    test_result=evaluate(engine,test);examples=test_result.pop('examples')
    report={'dataset':'Retailrocket','source':'https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset',
      'license':'CC BY-NC-SA 4.0','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'seed':SEED,
      'original_events':original,'deduplicated_events':len(events),'event_counts':events.event.value_counts().to_dict(),
      'data_start':date(start),'data_end':date(end),'cutoffs':{'retrieval_end':date(bounds[0]),'ranker_train_end':date(bounds[1]),'validation_end':date(bounds[2])},
      'retrieval':retrieval,'query_pool_sizes':dict(zip(['ranker_train','validation','test'],counts)),
      'query_sample_sizes':dict(zip(['ranker_train','validation','test'],list(map(len,sets)))),
      'train_audit':train_audit,'validation_audit':val_audit,'ranker_best_iteration':ranker.best_iteration_,
      'feature_importance':dict(zip(FEATURES,map(int,ranker.feature_importances_))),
      'validation':validation,'test':test_result,'elapsed_seconds':round(time.time()-begin,2),
      'environment':{'python':platform.python_version(),'lightgbm':lgb.__version__,'platform':platform.platform()},
      'evaluation_scope':'Next item outside the previous 20 interactions in a 30-minute session; at most 3 queries/session. Seeded reservoir sample within each time window. Unknown targets remain misses in evaluation. Single target per query, so hit rate equals recall.',
      'limitations':['Anonymized products: no real titles, photos or categories are inferred.',
       'Historical offline benchmark; no sales or conversion uplift is claimed.',
       'Sparse sessions without prior events are outside the primary evaluation; empty-profile behavior is tested separately.',
       'Catalog limited to frequent products selected before the retrieval cutoff. Unknown test targets count as misses.',
       'Positive target injection is used only for ranker training, never validation or test.',
       'User histories use only earlier session events. Item factors and statistics stay frozen after the first cutoff.',
       'Sequential interactions are not exposure logs; an unobserved candidate is not a verified dislike.',
       'Confidence intervals resample queries, not independent shoppers; interpret as descriptive.']}
    for folder in ['artifacts','reports']: (ROOT/folder).mkdir(exist_ok=True)
    bundle['metrics']=report;bundle['demo_examples']=examples
    joblib.dump(bundle,ROOT/'artifacts/model.joblib',compress=3)
    (ROOT/'reports/metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'reports/demo_examples.json').write_text(json.dumps(examples,indent=2)+'\n')
    log(stage='done',test=test_result,elapsed_seconds=report['elapsed_seconds'])

if __name__=='__main__':main()
