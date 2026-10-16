締切前の直前情報と単勝オッズを保存し、v4モデルを本番predictionsへ適用する実装。外部投稿や購入はしない。まだ本番切替していない。具体的な不具合・リーク・deadline判定の抜け・過剰取得・DBの破損条件を反証せよ。元の特徴量と99列/確率parity試験は別途実行中。コード全文:

FILE runner.py
"""Deadline-gated live predictions and win odds; never sends posts or buys bets."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
import datetime as dt, fcntl, hashlib, json, sqlite3, sys, time, traceback, urllib.request, urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'loop/vendor'))
import pandas as pd
import numpy as np
from sources import rows_from_json,parse_preview,parse_win_odds
from fast_features import Predictor
JST=ZoneInfo('Asia/Tokyo'); STATE=ROOT/'live/state'; STATE.mkdir(parents=True,exist_ok=True)

def now(): return dt.datetime.now(JST)
def digest(b): return hashlib.sha256(b).hexdigest()
def conn():
    c=sqlite3.connect(STATE/'live.db',timeout=30);c.row_factory=sqlite3.Row
    c.executescript('CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,day TEXT,url TEXT,started TEXT,finished TEXT,status INTEGER,sha256 TEXT,path TEXT);\nCREATE TABLE IF NOT EXISTS predictions(day TEXT,st INTEGER,r INTEGER,deadline TEXT,committed_at TEXT,record TEXT,PRIMARY KEY(day,st,r));\nCREATE TABLE IF NOT EXISTS events(created_at TEXT,kind TEXT,detail TEXT);\nCREATE TABLE IF NOT EXISTS control(key TEXT PRIMARY KEY,value TEXT);')
    return c

def event(kind,detail):
    with conn() as c:c.execute('INSERT INTO events VALUES (?,?,?)',(now().isoformat(),kind,str(detail)))
    print(now().isoformat(),kind,detail,flush=True)

def fetch(url):
    if (STATE/'STOP').exists():raise RuntimeError('STOP')
    with conn() as c:
        blocked=c.execute("SELECT value FROM control WHERE key='blocked_until'").fetchone()
        if blocked and now()<dt.datetime.fromisoformat(blocked[0]):raise RuntimeError('network cooldown')
        n=c.execute('SELECT count(*) FROM requests WHERE day=?',(str(now().date()),)).fetchone()[0]
        if n>=650:raise RuntimeError('daily request cap 650')
        last=c.execute('SELECT started FROM requests ORDER BY id DESC LIMIT 1').fetchone()
        if last:
            delay=5-(now()-dt.datetime.fromisoformat(last[0])).total_seconds()
            if delay>0:time.sleep(delay)
        started=now().isoformat()
        row=c.execute('INSERT INTO requests(day,url,started) VALUES (?,?,?)',(str(now().date()),url,started));rid=row.lastrowid
    status=0;data=b''
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'kyotei-db-research'})
        with urllib.request.urlopen(request,timeout=25) as resp:status=resp.status;data=resp.read()
    except urllib.error.HTTPError as e:
        status=e.code
        if status in (403,429):
            with conn() as c:c.execute('INSERT OR REPLACE INTO control VALUES (?,?)',('blocked_until',(now()+dt.timedelta(hours=1)).isoformat()))
        raise
    finally:
        finished=now().isoformat();path=STATE/'raw'/str(now().date())/f'{rid}.dat';path.parent.mkdir(parents=True,exist_ok=True)
        if data:path.write_bytes(data)
        with conn() as c:c.execute('UPDATE requests SET finished=?,status=?,sha256=?,path=? WHERE id=?',(finished,status,digest(data),str(path),rid))
    return data,dict(request_id=rid,url=url,started=started,finished=finished,sha256=digest(data),path=str(path))

def deadline_ok(deadline,observations,at=None):
    at=at or now();end=dt.datetime.fromisoformat(deadline)
    return at.tzinfo is not None and at.date()==end.date() and at<end-dt.timedelta(seconds=60) and all(dt.datetime.fromisoformat(x['finished'])<end and dt.datetime.fromisoformat(x['finished'])<=at for x in observations)

def save_candidate(record,primary_db,active,at=None):
    test_at=at
    at=at or now()
    if not deadline_ok(record['deadline'],record['sources'],at):raise ValueError('deadline or source time gate')
    if (STATE/'STOP').exists():raise RuntimeError('STOP')
    probs=record['probabilities']; assert set(probs)==set('123456') and abs(sum(probs.values())-1)<1e-8
    assert all(np.isfinite(v) and 0<v<1 for v in probs.values())
    order=sorted(range(1,7),key=lambda b:probs[str(b)],reverse=True)
    day,st,r=record['day'],record['st'],record['r']
    with conn() as c:
        if active:
            if not primary_db.exists(): raise FileNotFoundError(primary_db)
            c.execute('ATTACH DATABASE ? AS production',(str(primary_db),))
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM predictions WHERE day=? AND st=? AND r=?',(day,st,r)).fetchone():return False
        # Recheck while holding the transaction lock, immediately before mutation.
        committed=test_at or now()
        if not deadline_ok(record['deadline'],record['sources'],committed):raise ValueError('deadline after lock')
        old=None
        if active:
            row=c.execute('SELECT * FROM production.predictions WHERE race_date=? AND stadium_number=? AND race_number=?',(day,st,r)).fetchone()
            old=dict(row) if row else None
        record.update(committed_at=committed.isoformat(),legacy_prediction=old,primary=active)
        c.execute('INSERT INTO predictions VALUES (?,?,?,?,?,?)',(day,st,r,record['deadline'],committed.isoformat(),json.dumps(record,ensure_ascii=False)))
        if active:
            analysis='[v4-live] COMBINED+TrueSkill+course; before-deadline; model='+record['model_sha256']+'; odds stored separately'
            c.execute('INSERT OR REPLACE INTO production.predictions (race_date,stadium_number,race_number,predicted_order,confidence,recommended_bets,analysis) VALUES (?,?,?,?,?,?,?)',(day,st,r,json.dumps(order),probs[str(order[0])],'[]',analysis))
            # Prevent the old-model grade from being displayed against the new-model prediction.
            ps=[probs[str(b)] for b in order];p1=ps[0];p2=sum(ps[:2]);p3=sum(ps[:3]);grade='S' if p1>=.4 and p2>=.55 else 'A' if p1>=.3 and p2>=.45 else 'B' if p1>=.2 else 'C'
            row=c.execute('SELECT * FROM production.race_grades WHERE race_date=? AND stadium_number=? AND race_number=?',(day,st,r)).fetchone()
            record['legacy_grade']=dict(row) if row else None
            c.execute('INSERT OR REPLACE INTO production.race_grades (race_date,stadium_number,race_number,grade,top1_prob,top2_prob,top3_prob,reason) VALUES (?,?,?,?,?,?,?,?)',(day,st,r,grade,p1,p2,p3,'[v4-live] prediction probability; no profitability claim'))
            c.execute('UPDATE predictions SET record=? WHERE day=? AND st=? AND r=?',(json.dumps(record,ensure_ascii=False),day,st,r))
    return True

class Worker:
    def __init__(self):self.day=None;self.predictor=None;self.attempts={}
    def prepare(self,day):
        with sqlite3.connect(f'file:{ROOT}/data/races.db?mode=ro',uri=True) as c:history=pd.read_sql('select * from boats',c)
        history.date=pd.to_datetime(history.date)
        cached=STATE/'history';cached.mkdir(exist_ok=True)
        d=history.date.max().date()+dt.timedelta(days=1)
        while d<day:
            path=cached/f'{d:%Y%m%d}.json'
            if path.exists():data=path.read_bytes()
            else:
                data,_=fetch(f'https://boatraceopenapi.github.io/api/v1/{d.year}/{d:%Y%m%d}.json')
                if not json.loads(data).get('programs',{}).get('stadiums'):raise ValueError('missing history day')
                path.write_bytes(data)
            part=rows_from_json(json.loads(data)); assert (part.date==pd.Timestamp(d)).all()
            if len(part)==0 or part.place.notna().sum()==0:raise ValueError('unsettled history day')
            history=pd.concat([history,part],ignore_index=True);d+=dt.timedelta(days=1)
        self.program_bytes,self.program_source=fetch(f'https://boatraceopenapi.github.io/api/v1/{day.year}/{day:%Y%m%d}.json')
        self.today=rows_from_json(json.loads(self.program_bytes),mask=True)
        if self.today.empty or not (self.today.date==pd.Timestamp(day)).all():raise ValueError('wrong/empty programme date')
        if not self.today.groupby(['st','r']).boat.apply(lambda s:sorted(s)==[1,2,3,4,5,6]).all():raise ValueError('incomplete programme')
        with sqlite3.connect(f'file:{ROOT}/data/racers.db?mode=ro',uri=True) as c:kib=pd.read_sql('select * from kibetsu',c)
        kib['racer']=pd.to_numeric(kib.toban,errors='coerce');kib.period_to=pd.to_datetime(kib.period_to)
        self.modeldir=ROOT/'loop/models/202610'
        self.predictor=Predictor(history,kib,str(day),self.modeldir)
        self.day=day;self.attempts={}
        event('day_ready',dict(day=str(day),races=self.today.groupby(['st','r']).ngroups,history_rows=len(history)))

    def tick(self):
        at=now()
        if not 8<=at.hour<22:return
        if self.day!=at.date():self.prepare(at.date())
        config=json.loads((ROOT/'live/config.json').read_text()); active=config['active_model']=='v4'
        with conn() as c:done={(x['st'],x['r']) for x in c.execute('SELECT st,r FROM predictions WHERE day=?',(str(self.day),))}
        candidates=[]
        for (st,r),group in self.today.groupby(['st','r']):
            deadline=pd.Timestamp(group.closed_at.iloc[0]).to_pydatetime().replace(tzinfo=JST)
            remain=(deadline-now()).total_seconds()
            key=(int(st),int(r))
            if key in done or not 180<remain<=900:continue
            last,n=self.attempts.get(key,(0,0))
            if n>=2 or time.monotonic()-last<180:continue
            self.attempts[key]=(time.monotonic(),n+1)
            try:
                url=f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={r}&jcd={st:02d}&hd={self.day:%Y%m%d}'
                html,source=fetch(url); preview,official_deadline=parse_preview(html.decode('utf-8'),str(self.day),int(r))
                # Use the earlier deadline if sources disagree; never extend eligibility silently.
                end=min(deadline,dt.datetime.fromisoformat(official_deadline)).isoformat()
                if not deadline_ok(end,[self.program_source,source]):continue
                for b,values in preview.items():
                    mask=(self.today.st==st)&(self.today.r==r)&(self.today.boat==b)
                    if int(self.today.loc[mask,'racer'].iloc[0])!=values['racer']:raise ValueError('racer changed from programme')
                    for col,value in values.items():self.today.loc[mask,col]=value
                candidates.append((int(st),int(r),end,source))
            except Exception as e:event('preview_skip',dict(st=int(st),r=int(r),error=str(e)))
        if not candidates:return
        frame=self.predictor.build(self.today);frame['p']=self.predictor.probabilities(frame)
        for st,r,end,preview_source in candidates:
            try:
                if not deadline_ok(end,[self.program_source,preview_source]):raise ValueError('late feature computation')
                # Odds captured after inference, close to commit, never substituted with final payouts.
                html,odds_source=fetch(f'https://www.boatrace.jp/owpc/pc/race/oddstf?rno={r}&jcd={st:02d}&hd={self.day:%Y%m%d}')
                odds=parse_win_odds(html.decode('utf-8'))
                rows=frame[(frame.st==st)&(frame.r==r)]
                p={str(int(x.boat)):float(x.p) for x in rows.itertuples()};inv={str(k):1/v for k,v in odds.items()};total=sum(inv.values())
                record=dict(day=str(self.day),st=st,r=r,deadline=end,sources=[self.program_source,preview_source,odds_source],
                    probabilities=p,win_odds=odds,market_probabilities={k:v/total for k,v in inv.items()},
                    model_sha256=digest((self.modeldir/'manifest.json').read_bytes()),model='COMBINED+TrueSkill+course',
                    feature_values=json.loads(rows[['boat']+self.predictor.cols].loc[:,lambda x:~x.columns.duplicated()].to_json(orient='records')),
                    source_mode='pre_deadline',history_cutoff=str(self.day-dt.timedelta(days=1)))
                saved=save_candidate(record,Path(config['primary_db']),active)
                event('prediction_saved',dict(st=st,r=r,saved=saved,primary=active))
            except Exception as e:event('prediction_skip',dict(st=st,r=r,error=str(e)))

if __name__=='__main__':
    with (STATE/'worker.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:sys.exit('worker already running')
        worker=Worker()
        while True:
            try:
                if (STATE/'STOP').exists():event('stopped','STOP file')
                else:worker.tick()
                (STATE/'heartbeat.json').write_text(json.dumps(dict(at=now().isoformat(),day=str(worker.day),ready=worker.predictor is not None,stop=(STATE/'STOP').exists())))
            except Exception as e:
                event('worker_error',str(e));traceback.print_exc();time.sleep(30)
            if '--once' in sys.argv:break
            time.sleep(30)


FILE sources.py
import json, re
import pandas as pd
from bs4 import BeautifulSoup
COLS = ['date', 'st', 'r', 'grade', 'distance', 'day_number', 'closed_at', 'title', 'boat', 'racer', 'name', 'rank', 'branch', 'age', 'weight', 'f', 'l', 'avg_st', 'nat_win', 'nat_top2', 'nat_top3', 'loc_win', 'loc_top2', 'loc_top3', 'motor', 'motor_top2', 'motor_top3', 'boatno', 'boat_top2', 'boat_top3', 'pv_wind', 'pv_wind_dir', 'pv_wave', 'pv_weather', 'pv_air', 'pv_water', 'pv_course', 'pv_st', 'pv_weight', 'pv_ex_time', 'pv_tilt', 'rs_course', 'rs_st', 'place', 'technique']

def rows_from_json(obj, mask=False):
    rows=[]
    for st,sd in obj.get('programs',{}).get('stadiums',{}).items():
        for r,rc in sd.get('races',{}).items():
            pv={} if mask else (rc.get('preview') or {})
            rs={} if mask else (rc.get('result') or {})
            for b,x in (rc.get('racers') or {}).items():
                p=(pv.get('racers') or {}).get(b) or {}; q=(rs.get('racers') or {}).get(b) or {}; g=x.get
                rows.append([
                    rc.get('date'), int(st), int(r), rc.get('grade_number'), rc.get('distance'), rc.get('day_number'), rc.get('closed_at'), rc.get('title'),
                    int(b), g('number'), g('name'), g('rank_number'), g('branch_number'), g('age'), g('weight'), g('flying_count'), g('late_count'), g('average_start_timing'),
                    g('national_win_rate'), g('national_top_2_percent'), g('national_top_3_percent'), g('local_win_rate'), g('local_top_2_percent'), g('local_top_3_percent'),
                    g('motor_number'), g('motor_top_2_percent'), g('motor_top_3_percent'), g('boat_number'), g('boat_top_2_percent'), g('boat_top_3_percent'),
                    pv.get('wind_speed'), pv.get('wind_direction_number'), pv.get('wave_height'), pv.get('weather_number'), pv.get('air_temperature'), pv.get('water_temperature'),
                    p.get('course_number'), p.get('start_timing'), p.get('weight'), p.get('exhibition_time'), p.get('tilt_adjustment'),
                    q.get('course_number'), q.get('start_timing'), q.get('place_number'), rs.get('technique_number')])
    df=pd.DataFrame(rows,columns=COLS)
    df['date']=pd.to_datetime(df.date)
    return df

def number(txt):
    txt=txt.strip().replace('F','-').replace('L','')
    m=re.search(r'-?(?:\d+\.?\d*|\.\d+)',txt)
    return float(m.group()) if m else None

def parse_preview(html,day,race_no):
    s=BeautifulSoup(html,'html.parser'); rows={}
    for body in s.select('table.is-w748 tbody'):
        cells=body.select('tr')[0].find_all('td',recursive=False)
        if len(cells)<6: continue
        b=number(cells[0].get_text())
        if b not in range(1,7): continue
        link=cells[2].select_one('a[href*=toban]')
        if not link: continue
        racer=int(re.search(r'toban=(\d+)',link['href']).group(1))
        rows[int(b)]=dict(racer=racer,pv_weight=number(cells[3].get_text()),pv_ex_time=number(cells[4].get_text()),pv_tilt=number(cells[5].get_text()))
    for course,div in enumerate(s.select('div.table1_boatImage1'),1):
        b=int(div.select_one('.table1_boatImage1Number').get_text(strip=True))
        if b in rows: rows[b].update(pv_course=course,pv_st=number(div.select_one('.table1_boatImage1Time').get_text()))
    weather={}
    for selector,key in [('is-direction','pv_air'),('is-waterTemperature','pv_water'),('is-wave','pv_wave'),('is-wind','pv_wind')]:
        node=s.select_one(f'.weather1_bodyUnit.{selector} .weather1_bodyUnitLabelData')
        weather[key]=number(node.get_text()) if node else None
    for selector,pattern,key in [('.is-weather .weather1_bodyUnitImage',r'is-weather(\d+)','pv_weather'),('.is-windDirection .weather1_bodyUnitImage',r'is-wind(\d+)','pv_wind_dir')]:
        node=s.select_one(selector); match=re.search(pattern,' '.join(node.get('class',[]))) if node else None
        weather[key]=int(match.group(1)) if match else None
    deadline=None
    for table in s.select('table'):
        body=table.find('tbody')
        if body and '締切予定時刻' in body.get_text():
            cells=body.select('td')
            if len(cells)>=13:
                hm=cells[race_no].get_text(strip=True)
                if re.fullmatch(r'\d{2}:\d{2}',hm): deadline=f'{day}T{hm}:00+09:00'
            break
    if set(rows)!=set(range(1,7)) or deadline is None: raise ValueError('missing six preview boats/deadline')
    for row in rows.values():
        row.update(weather)
        if any(row.get(k) is None for k in ['pv_ex_time','pv_course','pv_st','pv_weight','pv_air','pv_water','pv_wave','pv_weather']):
            raise ValueError('incomplete exhibition')
        if not 5<row['pv_ex_time']<9: raise ValueError('invalid exhibition time')
    if sorted(x['pv_course'] for x in rows.values())!=list(range(1,7)): raise ValueError('invalid courses')
    return rows,deadline

def parse_win_odds(html):
    s=BeautifulSoup(html,'html.parser')
    h=s.find('span',class_='title7_mainLabel',string='単勝オッズ')
    if h is None: raise ValueError('no win odds')
    table=h.find_parent('div',class_='grid_unit').find('table'); out={}
    for body in table.find_all('tbody'):
        cells=body.find('tr').find_all('td')
        if len(cells)>=3:
            b=number(cells[0].get_text()); v=number(cells[2].get_text())
            if b in range(1,7) and v and v>=1: out[int(b)]=v
    if set(out)!=set(range(1,7)): raise ValueError('incomplete six-boat win odds')
    return out


FILE fast_features.py
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


FILE test_live.py
import sys,tempfile,unittest,json,sqlite3,datetime as dt,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'loop/vendor'))
import runner
from sources import rows_from_json,parse_preview,parse_win_odds

class LiveTests(unittest.TestCase):
    def test_real_parser_matches_api(self):
        f=ROOT/'live/fixtures';obj=json.loads((f/'v1.txt').read_text());df=rows_from_json(obj)
        rows,deadline=parse_preview((f/'beforeinfo_02.txt').read_text(),'2026-10-15',12)
        for b,row in rows.items():
            truth=df[(df.st==2)&(df.r==12)&(df.boat==b)].iloc[0]
            for k,v in row.items():self.assertEqual(truth[k],v)
        self.assertEqual(deadline,'2026-10-15T16:25:00+09:00')
        self.assertEqual(set(parse_win_odds((f/'oddstf_02.txt').read_text())),set(range(1,7)))
        with self.assertRaises(ValueError):parse_preview('<html/>','2026-10-15',12)
    def record(self):
        return dict(day='2026-10-16',st=2,r=1,deadline='2026-10-16T12:00:00+09:00',sources=[{'finished':'2026-10-16T11:55:00+09:00'}],probabilities={str(i):1/6 for i in range(1,7)},model_sha256='test')
    def test_deadline_boundary_and_future_fetch(self):
        r=self.record();before=dt.datetime.fromisoformat('2026-10-16T11:58:59+09:00')
        self.assertTrue(runner.deadline_ok(r['deadline'],r['sources'],before))
        self.assertFalse(runner.deadline_ok(r['deadline'],r['sources'],before+dt.timedelta(seconds=1)))
        self.assertFalse(runner.deadline_ok(r['deadline'],[{'finished':'2026-10-16T12:00:00+09:00'}],before))
    def test_atomic_primary_and_duplicate(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=Path(td)/'production.db'
            schema=(ROOT/'live/base/src/boatrace_ai/storage/schema.sql').read_text()
            with sqlite3.connect(db) as c:
                c.executescript(schema)
                c.execute("INSERT INTO predictions (race_date,stadium_number,race_number,predicted_order,confidence,recommended_bets,analysis) VALUES ('2026-10-16',2,1,'[2,1,3,4,5,6]',.3,'[]','old')")
            at=dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            self.assertTrue(runner.save_candidate(self.record(),db,True,at))
            self.assertFalse(runner.save_candidate(self.record(),db,True,at))
            with sqlite3.connect(db) as c:self.assertTrue(c.execute('SELECT analysis FROM predictions').fetchone()[0].startswith('[v4-live]'))
            with runner.conn() as c:
                record=json.loads(c.execute('SELECT record FROM predictions').fetchone()[0]);self.assertEqual(record['legacy_prediction']['analysis'],'old')
            (Path(td)/'STOP').touch()
            with self.assertRaises(RuntimeError):runner.save_candidate(self.record(),db,True,at)
    def test_lock_delay_rechecks_time(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            early=dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00');late=dt.datetime.fromisoformat('2026-10-16T12:00:00+09:00')
            with patch.object(runner,'now',side_effect=[early,late]):
                with self.assertRaises(ValueError):runner.save_candidate(self.record(),Path(td)/'unused',False)
            with runner.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM predictions').fetchone()[0],0)
if __name__=='__main__':unittest.main()
