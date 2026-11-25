import json,os,secrets,sqlite3,time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI,HTTPException,Request,Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from .engine import ROOT,load_engine

app=FastAPI(title='RetailRank',version='1.0.0',description='Two-stage recommendation research demo')
app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
COOKIE='retailrank_session'

@contextmanager
def connection():
    path=Path(os.environ.get('RETAILRANK_DB',ROOT/'runtime/demo.sqlite3'))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10)
    db.row_factory=sqlite3.Row
    db.executescript('''CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,created_at REAL);
      CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,item_id INTEGER,event TEXT,created_at REAL);
      CREATE INDEX IF NOT EXISTS actions_session ON actions(session_id,id);
      CREATE TABLE IF NOT EXISTS impressions(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,method TEXT,model_version TEXT,items TEXT,latency_ms REAL,created_at REAL);''')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def session(request,response):
    value=request.cookies.get(COOKIE,'')
    with connection() as db:
        found=db.execute('SELECT id FROM sessions WHERE id=?',(value,)).fetchone() if len(value)==43 else None
        if not found:
            value=secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?)',(value,time.time()))
            response.set_cookie(COOKIE,value,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=7*86400)
    return value

def check_origin(request):
    origin=request.headers.get('origin')
    if origin and urlparse(origin).netloc!=request.headers.get('host'):
        raise HTTPException(403,'Use the app from its own origin.')

def history(sid):
    with connection() as db:
        rows=db.execute('SELECT item_id,event FROM actions WHERE session_id=? ORDER BY id DESC LIMIT 20',(sid,)).fetchall()
    return [dict(r) for r in reversed(rows)]

class Action(BaseModel):
    item_id:int=Field(ge=0)
    event:Literal['view','addtocart','transaction']

@app.get('/')
def index():return FileResponse(ROOT/'web/index.html')

@app.get('/api/health')
def health():
    engine=load_engine()
    return {'status':'ok','catalog_size':len(engine.ids),'model_version':engine.bundle['model_version']}

@app.get('/api/metrics')
def metrics():return load_engine().bundle['metrics']

@app.get('/api/state')
def state(request:Request,response:Response):
    sid=session(request,response)
    with connection() as db:
        counts=dict(db.execute('SELECT event,COUNT(*) FROM actions WHERE session_id=? GROUP BY event',(sid,)).fetchall())
        impressions=db.execute('SELECT COUNT(*) FROM impressions WHERE session_id=?',(sid,)).fetchone()[0]
    return {'history':history(sid),'counts':counts,'recommendation_requests':impressions}

@app.post('/api/actions')
def action(item:Action,request:Request,response:Response):
    check_origin(request)
    if item.item_id not in load_engine().lookup:raise HTTPException(404,'Item is outside the trained catalog.')
    sid=session(request,response)
    with connection() as db:
        db.execute('INSERT INTO actions(session_id,item_id,event,created_at) VALUES(?,?,?,?)',(sid,item.item_id,item.event,time.time()))
    return {'saved':True,'history':history(sid)}

@app.post('/api/reset')
def reset(request:Request,response:Response):
    check_origin(request);sid=session(request,response)
    with connection() as db:
        db.execute('DELETE FROM actions WHERE session_id=?',(sid,))
        db.execute('DELETE FROM impressions WHERE session_id=?',(sid,))
    return {'reset':True}

@app.get('/api/recommendations')
def recommendations(request:Request,response:Response,method:Literal['ranker','als','similarity','popular']='ranker',k:int=10):
    if not 1<=k<=50:raise HTTPException(422,'k must be between 1 and 50')
    sid=session(request,response);begin=time.perf_counter()
    result=load_engine().recommend(history(sid),k,method)
    result['latency_ms']=round((time.perf_counter()-begin)*1000,3)
    with connection() as db:
        db.execute('INSERT INTO impressions(session_id,method,model_version,items,latency_ms,created_at) VALUES(?,?,?,?,?,?)',
          (sid,result['method'],result['model_version'],json.dumps([i['item_id'] for i in result['items']]),result['latency_ms'],time.time()))
    return result

@app.get('/api/catalog')
def catalog(q:str='',offset:int=0,limit:int=24):
    if offset<0 or not 1<=limit<=100 or len(q)>20:raise HTTPException(422,'Invalid catalog query')
    engine=load_engine();ids=engine.popular
    if q:ids=[i for i in ids if q in str(int(engine.ids[i]))]
    return {'total':len(ids),'items':[{'item_id':int(engine.ids[i]),'training_events':int(engine.stats[i,0])} for i in ids[offset:offset+limit]]}

@app.get('/api/scenarios')
def scenarios():
    return {'scenarios':[{'id':i,'history_length':len(q['history']),'recorded_at':q['timestamp']} for i,q in enumerate(load_engine().bundle['demo_examples'])]}

@app.post('/api/scenarios/{index}')
def replay(index:int,request:Request,response:Response):
    check_origin(request);examples=load_engine().bundle['demo_examples']
    if not 0<=index<len(examples):raise HTTPException(404,'Unknown replay')
    sid=session(request,response);q=examples[index]
    with connection() as db:
        db.execute('DELETE FROM actions WHERE session_id=?',(sid,))
        for item in q['history']:
            db.execute('INSERT INTO actions(session_id,item_id,event,created_at) VALUES(?,?,?,?)',(sid,item['item_id'],item['event'],time.time()))
    # Target is disclosed only as replay ground truth; it is never passed to recommendation logic.
    return {'loaded':True,'history':q['history'],'actual_next_item':q['target'],'target_event':q['target_event'],
            'notice':'Historical test replay. The next item was excluded from the profile used to make recommendations.'}
