import sys, json, hashlib, time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
import trueskill
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'model_exp'))
import features_v4 as f4
from features import RESULT_COLS

class Predictor:
    def __init__(self,history,kib,day,modeldir):
        self.day=pd.Timestamp(day); self.history=history[history.date<self.day].copy(); self.kib=kib
        self.meta=json.loads((modeldir/'manifest.json').read_text()); self.cols=self.meta['columns']
        for name,digest in self.meta['models'].items():
            assert hashlib.sha256((modeldir/name).read_bytes()).hexdigest()==digest
        for name in ['features.py','features_v3.py','features_v4.py']:
            assert hashlib.sha256((ROOT/'model_exp'/name).read_bytes()).hexdigest()==self.meta['code'][name]
        assert hashlib.sha256((ROOT/'data/racers.db').read_bytes()).hexdigest()==self.meta['code']['racers.db']
        assert pd.Timestamp(self.meta['tune_max'])<self.day
        self.models=[lgb.Booster(model_file=str(modeldir/f'{s}.txt')) for s in self.meta['seeds']]
        assert all(m.feature_name()==self.cols for m in self.models)
        env=trueskill.TrueSkill(mu=25.,sigma=25./3,beta=25./6,tau=25./300,draw_probability=.01)
        self.ratings={'ts':{},'tsc':{}}; self.counts={'ts':{},'tsc':{}}
        hist=self.history.sort_values(['date','st','r','boat'])
        assert not hist.duplicated(['date','st','r','boat']).any()
        for _,g in hist.groupby(['date','st','r'],sort=False):
            g=g[g.place.notna()]
            if len(g)<2: continue
            if g.racer.duplicated().any(): raise ValueError('duplicate racer in history')
            ranks=list(np.clip(g.place.values,1,6).astype(int))
            for prefix,keys in [('ts',[(float(x),) for x in g.racer]),('tsc',list(zip(g.racer.astype(float),g.rs_course.fillna(g.boat).astype(float))))]:
                R=self.ratings[prefix]; N=self.counts[prefix]
                updated=env.rate([(R.get(k,env.create_rating()),) for k in keys],ranks=ranks)
                for k,(rating,) in zip(keys,updated): R[k]=rating; N[k]=N.get(k,0)+1
        self.original=f4._trueskill

    def cached_ts(self,df,key_upd,key_look,prefix):
        sel=df.date==self.day; indexes=np.flatnonzero(sel)
        mu=np.full(len(df),np.nan); sg=mu.copy(); n=mu.copy()
        keys=list(zip(*[df.loc[sel,k].astype(float) for k in key_look]))
        for i,k in zip(indexes,keys):
            rating=self.ratings[prefix].get(k)
            mu[i]=rating.mu if rating else 25.; sg[i]=rating.sigma if rating else 25./3
            n[i]=self.counts[prefix].get(k,0)
        df[f'{prefix}_mu']=mu; df[f'{prefix}_sigma']=sg; df[f'{prefix}_n']=n
        df[f'{prefix}_cons']=mu-3*sg
        df[f'{prefix}_rank']=df.groupby('race_id')[f'{prefix}_mu'].rank(ascending=False)
        df[f'{prefix}_gap_best']=mu-df.groupby('race_id')[f'{prefix}_mu'].transform('max')
        df[f'{prefix}_dm']=f4.diff_mean(df,f'{prefix}_mu')
        return [f'{prefix}_{s}' for s in ['mu','sigma','n','cons','rank','gap_best','dm']]

    def build(self,today,reference=False):
        assert (today.date==self.day).all()
        today=today.copy(); today[RESULT_COLS]=np.nan
        raw=pd.concat([self.history,today],ignore_index=True)
        start=time.monotonic()
        f4._trueskill=self.original if reference else self.cached_ts
        try: df,_=f4.build4(raw,self.kib)
        finally: f4._trueskill=self.original
        out=df[df.date==self.day].sort_values(['st','r','boat']).reset_index(drop=True)
        assert len(out)==len(today)
        print('build_seconds',round(time.monotonic()-start,3),'reference',reference,flush=True)
        return out

    def probabilities(self,frame):
        p=sum(m.predict(frame[self.cols],num_threads=2) for m in self.models)/len(self.models)
        x=pd.Series(self.meta['T']*np.log(np.clip(p,1e-12,None)))
        e=np.exp(x-x.groupby(frame.race_id.values).transform('max'))
        p=(e/e.groupby(frame.race_id.values).transform('sum')).values
        assert np.isfinite(p).all() and (p>0).all()
        return p
