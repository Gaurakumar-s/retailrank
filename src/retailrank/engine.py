"""Shared offline/online retrieval and ranking. No online training is implied."""
from pathlib import Path
from functools import lru_cache
import os
import joblib
import numpy as np

ROOT=Path(os.environ.get('RETAILRANK_HOME',Path(__file__).resolve().parents[2]))
FEATURES=['als_score','profile_similarity','max_history_similarity','last_item_similarity',
          'mean_history_similarity','log_popularity','cart_rate','purchase_rate',
          'recent_popularity_share','history_length','history_cart_share','history_purchase_share']
WEIGHTS={'view':1.0,'addtocart':3.0,'transaction':6.0}

class Engine:
    def __init__(self,bundle):
        self.bundle=bundle
        self.ids=np.array(bundle['item_ids'],dtype=np.int64)
        self.lookup={int(v):i for i,v in enumerate(self.ids)}
        self.factors=np.array(bundle['item_factors'],dtype=np.float32)
        norm=np.linalg.norm(self.factors,axis=1,keepdims=True)
        self.normalized=self.factors/np.maximum(norm,1e-8)
        self.base=self.factors.T@self.factors+np.eye(self.factors.shape[1],dtype=np.float32)*bundle['regularization']
        self.stats=np.array(bundle['item_stats'],dtype=np.float32)
        self.popular=np.argsort(-self.stats[:,0],kind='stable')
        self.ranker=bundle.get('ranker')

    def encode(self,history):
        return [(self.lookup[int(h['item_id'])],WEIGHTS[h['event']]) for h in history[-20:] if int(h['item_id']) in self.lookup]

    def context(self,history):
        encoded=self.encode(history)
        if not encoded:
            return np.zeros(len(self.ids),dtype=np.float32),np.zeros(len(self.ids),dtype=np.float32),encoded
        idx,weights=zip(*encoded)
        unique,inv=np.unique(idx,return_inverse=True)
        total=np.bincount(inv,weights=weights)
        confidence=1+15*np.log1p(total)
        y=self.factors[unique]
        a=self.base+y.T@((confidence-1)[:,None]*y)
        b=y.T@confidence
        profile=np.linalg.solve(a,b).astype(np.float32)
        als=self.factors@profile
        recency=np.arange(1,len(idx)+1,dtype=np.float32)
        interest=np.average(self.normalized[list(idx)],axis=0,weights=recency*np.array(weights))
        similar=self.normalized@interest
        return als,similar,encoded

    @staticmethod
    def top(scores,n,excluded=()):
        scores=np.array(scores,copy=True)
        if len(excluded):scores[list(excluded)]=-np.inf
        count=min(n,int(np.isfinite(scores).sum()))
        if count<=0:return np.array([],dtype=np.int64)
        ids=np.argpartition(-scores,count-1)[:count]
        return ids[np.lexsort((ids,-scores[ids]))]

    def candidates(self,history,n=120):
        als,similar,encoded=self.context(history)
        excluded=set(i for i,w in encoded)
        if not encoded:
            ids=self.popular[:n]
        else:
            ids=np.unique(np.concatenate([self.top(als,60,excluded),self.top(similar,60,excluded),
                np.array([i for i in self.popular[:60] if i not in excluded][:20],dtype=np.int64)]))
        return ids,als,similar,encoded

    def features(self,candidates,als,similar,encoded):
        if encoded:
            idx,weights=zip(*encoded)
            sims=self.normalized[candidates]@self.normalized[list(idx)].T
            hist=[len(encoded),np.mean(np.array(weights)==3),np.mean(np.array(weights)==6)]
            extra=[sims.max(axis=1),sims[:,-1],sims.mean(axis=1)]
        else:
            hist=[0,0,0];extra=[np.zeros(len(candidates))]*3
        stats=self.stats[candidates]
        return np.column_stack([als[candidates],similar[candidates],*extra,
          np.log1p(stats[:,0]),stats[:,1],stats[:,2],stats[:,3],
          *[np.full(len(candidates),v) for v in hist]]).astype(np.float32)

    def rank_indices(self,history,k=10,method='ranker'):
        if k<1 or k>50:raise ValueError('k must be between 1 and 50')
        candidates,als,similar,encoded=self.candidates(history)
        excluded=set(i for i,w in encoded)
        if method=='popular' or not encoded:
            return np.array([i for i in self.popular if i not in excluded][:k]),None,len(candidates)
        if method=='als':return self.top(als,k,excluded),None,len(candidates)
        if method=='similarity':return self.top(similar,k,excluded),None,len(candidates)
        if method!='ranker':raise ValueError('Unknown recommendation method')
        if self.ranker is None:raise ValueError('Ranker has not been trained')
        x=self.features(candidates,als,similar,encoded)
        scores=self.ranker.booster_.predict(x,num_threads=2)
        order=np.lexsort((candidates,-scores))[:k]
        return candidates[order],scores[order],len(candidates)

    def recommend(self,history,k=10,method='ranker'):
        indices,scores,count=self.rank_indices(history,k,method)
        known=bool(self.encode(history))
        result=[]
        for rank,i in enumerate(indices):
            explanation='Popular in the training period'
            if known and method!='popular':
                recent=self.encode(history)
                source=max(recent,key=lambda pair:float(self.normalized[i]@self.normalized[pair[0]]))
                explanation=f'Behavioral similarity to item #{int(self.ids[source[0]])}'
            result.append({'item_id':int(self.ids[i]),'rank':rank+1,'score':None if scores is None else float(scores[rank]),
                           'reason':explanation,'training_events':int(self.stats[i,0])})
        return {'items':result,'method':method if known else 'popular','cold_start':not known,
                'candidate_count':count,'model_version':self.bundle['model_version'],
                'note':'Ranking scores are not purchase probabilities. Actions update the profile; model weights remain fixed.'}

@lru_cache(maxsize=1)
def load_engine():
    # Trusted, locally generated artifact only. Never deserialize an uploaded model.
    return Engine(joblib.load(ROOT/'artifacts/model.joblib'))
