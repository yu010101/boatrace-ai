前回最後の指摘「本番書込関数のatテスト引数で実時計迂回」を修正。save_candidateは3引数のみで時刻入力を受け付けず実時計now()のみ使用、テスト側だけunittest.mockでnowを差替。本番Workerに時刻上書き経路なし。phase1で予測のみcommit→実時計確認→phase2で本番へ反映。前回指摘の抜けが残るか、重大な実装の反例を反証せよ。
実際のコマンド: python live/test_live.py
..........
----------------------------------------------------------------------
Ran 10 tests in 0.287s

OK

"""Deadline-gated live predictions and win odds; never sends posts or buys bets."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
import datetime as dt, fcntl, hashlib, json, sqlite3, sys, time, traceback, urllib.request, urllib.error, uuid
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
        with urllib.request.urlopen(request,timeout=25) as resp:
            if resp.geturl()!=url: raise ValueError('unexpected redirect')
            status=resp.status;data=resp.read()
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

def primary_connection(path):
    if not path.exists(): raise FileNotFoundError(path)
    c=sqlite3.connect(path,timeout=20);c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS live_v4_predictions(day TEXT,st INTEGER,r INTEGER,deadline TEXT,committed_at TEXT,record TEXT,PRIMARY KEY(day,st,r))')
    c.commit();return c

def restore_primary(c,record):
    key=(record['day'],record['st'],record['r']);conflicts=[]
    for table,field,expected_field in [('predictions','legacy_prediction','applied_prediction'),('race_grades','legacy_grade','applied_grade')]:
        current=c.execute(f'SELECT * FROM {table} WHERE race_date=? AND stadium_number=? AND race_number=?',key).fetchone()
        expected=record.get(expected_field)
        if current is None or expected is None:continue
        if dict(current)!=expected:conflicts.append(table);continue
        old=record.get(field)
        if old is None:c.execute(f'DELETE FROM {table} WHERE race_date=? AND stadium_number=? AND race_number=?',key)
        else:
            cols=[k for k in old if k!='id']
            c.execute(f'UPDATE {table} SET '+','.join(f'{k}=?' for k in cols)+' WHERE race_date=? AND stadium_number=? AND race_number=?',[old[k] for k in cols]+list(key))
    return conflicts

def save_candidate(record,primary_db,active):
    at=now()
    if not deadline_ok(record['deadline'],record['sources'],at):raise ValueError('deadline or source time gate')
    if (STATE/'STOP').exists():raise RuntimeError('STOP')
    probs=record['probabilities']; assert set(probs)==set('123456') and abs(sum(probs.values())-1)<1e-8
    assert all(np.isfinite(v) and 0<v<1 for v in probs.values())
    order=sorted(range(1,7),key=lambda b:probs[str(b)],reverse=True)
    day,st,r=record['day'],record['st'],record['r']
    c=primary_connection(primary_db) if active else conn();table='live_v4_predictions' if active else 'predictions'
    try:
        c.execute('BEGIN IMMEDIATE')
        old_record=c.execute(f'SELECT committed_at FROM {table} WHERE day=? AND st=? AND r=?',(day,st,r)).fetchone()
        if old_record and old_record[0] is not None:c.rollback();return False
        if (STATE/'STOP').exists() or not deadline_ok(record['deadline'],record['sources'],now()):raise ValueError('lock deadline/STOP gate')
        # Phase 1 persists the forecast ONLY. No user-facing production row changes yet.
        record.update(primary=active,operation_status='forecast_pending_confirmation',operation_token=uuid.uuid4().hex)
        c.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?) ON CONFLICT(day,st,r) DO UPDATE SET deadline=excluded.deadline,record=excluded.record',(day,st,r,record['deadline'],None,json.dumps(record,ensure_ascii=False)))
        c.commit()
        persisted=now()
        if (STATE/'STOP').exists() or not deadline_ok(record['deadline'],record['sources'],persisted):raise ValueError('forecast persistence crossed deadline; primary untouched')
        record.update(forecast_persisted_at=persisted.isoformat(),pre_deadline_verified=True,operation_status='confirmed')
        # Phase 2 can expose only the already persisted and timestamp-verified forecast.
        # Audit/old-row backup and primary upserts use ONE database transaction.
        c.execute('BEGIN IMMEDIATE')
        owned=c.execute(f'SELECT committed_at,record FROM {table} WHERE day=? AND st=? AND r=?',(day,st,r)).fetchone()
        if owned is None or owned[0] is not None or json.loads(owned[1]).get('operation_token')!=record['operation_token']:raise ValueError('forecast ownership changed')
        if (STATE/'STOP').exists() or not deadline_ok(record['deadline'],record['sources'],now()):raise ValueError('application deadline/STOP gate')
        if active:
            row=c.execute('SELECT * FROM predictions WHERE race_date=? AND stadium_number=? AND race_number=?',(day,st,r)).fetchone();record['legacy_prediction']=dict(row) if row else None
            row=c.execute('SELECT * FROM race_grades WHERE race_date=? AND stadium_number=? AND race_number=?',(day,st,r)).fetchone();record['legacy_grade']=dict(row) if row else None
            analysis='[v4-live] COMBINED+TrueSkill+course; model='+record['model_sha256']+'; forecast recorded='+persisted.isoformat()
            c.execute('INSERT INTO predictions (race_date,stadium_number,race_number,predicted_order,confidence,recommended_bets,analysis) VALUES (?,?,?,?,?,?,?) ON CONFLICT(race_date,stadium_number,race_number) DO UPDATE SET predicted_order=excluded.predicted_order,confidence=excluded.confidence,recommended_bets=excluded.recommended_bets,analysis=excluded.analysis,created_at=CURRENT_TIMESTAMP',(day,st,r,json.dumps(order),probs[str(order[0])],'[]',analysis))
            ps=[probs[str(b)] for b in order];p1=ps[0];p2=sum(ps[:2]);p3=sum(ps[:3]);grade='S' if p1>=.4 and p2>=.55 else 'A' if p1>=.3 and p2>=.45 else 'B' if p1>=.2 else 'C'
            c.execute('INSERT INTO race_grades (race_date,stadium_number,race_number,grade,top1_prob,top2_prob,top3_prob,reason) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(race_date,stadium_number,race_number) DO UPDATE SET grade=excluded.grade,top1_prob=excluded.top1_prob,top2_prob=excluded.top2_prob,top3_prob=excluded.top3_prob,reason=excluded.reason,created_at=CURRENT_TIMESTAMP',(day,st,r,grade,p1,p2,p3,'[v4-live] prediction probability; no profitability claim'))
            record['applied_prediction']=dict(c.execute('SELECT * FROM predictions WHERE race_date=? AND stadium_number=? AND race_number=?',(day,st,r)).fetchone())
            record['applied_grade']=dict(c.execute('SELECT * FROM race_grades WHERE race_date=? AND stadium_number=? AND race_number=?',(day,st,r)).fetchone())
        checked=now()
        if (STATE/'STOP').exists() or not deadline_ok(record['deadline'],record['sources'],checked):raise ValueError('pre-commit deadline/STOP gate')
        record['application_checked_at']=checked.isoformat()
        c.execute(f'UPDATE {table} SET committed_at=?,record=? WHERE day=? AND st=? AND r=?',(persisted.isoformat(),json.dumps(record,ensure_ascii=False),day,st,r));c.commit()
        return True
    except Exception:c.rollback();raise
    finally:c.close()

class Worker:
    def __init__(self):self.day=None;self.predictor=None;self.attempts={}
    def prepare(self,day):
        with sqlite3.connect(f'file:{ROOT}/data/races.db?mode=ro',uri=True) as c:history=pd.read_sql('select * from boats',c)
        history.date=pd.to_datetime(history.date)
        cached=STATE/'history';cached.mkdir(exist_ok=True)
        d=history.date.max().date()+dt.timedelta(days=1)
        while d<day:
            path=cached/f'{d:%Y%m%d}.json'
            part=None
            if path.exists():
                candidate=rows_from_json(json.loads(path.read_bytes()))
                if len(candidate)>0 and candidate.place.notna().all():part=candidate
            if part is None:
                data,_=fetch(f'https://boatraceopenapi.github.io/api/v1/{d.year}/{d:%Y%m%d}.json')
                part=rows_from_json(json.loads(data))
                if part.empty or not (part.date==pd.Timestamp(d)).all() or part.place.isna().any():
                    raise ValueError('unsettled/cancelled history day requires review: '+str(d))
                path.write_bytes(data)
            assert (part.date==pd.Timestamp(d)).all()
            history=pd.concat([history,part],ignore_index=True);d+=dt.timedelta(days=1)
        self.program_bytes,self.program_source=fetch(f'https://boatraceopenapi.github.io/api/v1/{day.year}/{day:%Y%m%d}.json')
        self.today=rows_from_json(json.loads(self.program_bytes),mask=True)
        if self.today.empty or not (self.today.date==pd.Timestamp(day)).all():raise ValueError('wrong/empty programme date')
        if not self.today.groupby(['st','r']).boat.apply(lambda s:sorted(s)==[1,2,3,4,5,6]).all():raise ValueError('incomplete programme')
        with sqlite3.connect(f'file:{ROOT}/data/racers.db?mode=ro',uri=True) as c:kib=pd.read_sql('select * from kibetsu',c)
        kib['racer']=pd.to_numeric(kib.toban,errors='coerce');kib.period_to=pd.to_datetime(kib.period_to)
        self.modeldir=ROOT/'loop/models/202610'
        self.predictor=Predictor(history,kib,str(day),self.modeldir)
        self.day=day;self.attempts={};self.program_loaded=time.monotonic()
        event('day_ready',dict(day=str(day),races=self.today.groupby(['st','r']).ngroups,history_rows=len(history)))

    def tick(self):
        at=now()
        if not 8<=at.hour<22:return
        if self.day!=at.date():self.prepare(at.date())
        if self.day>=dt.date(2026,11,1):raise RuntimeError('frozen October model expired; review/retrain required')
        if time.monotonic()-self.program_loaded>3600:
            data,source=fetch(f'https://boatraceopenapi.github.io/api/v1/{self.day.year}/{self.day:%Y%m%d}.json')
            refreshed=rows_from_json(json.loads(data),mask=True)
            if refreshed.empty or not (refreshed.date==pd.Timestamp(self.day)).all():raise ValueError('invalid programme refresh')
            if not refreshed.groupby(['st','r']).boat.apply(lambda s:sorted(s)==[1,2,3,4,5,6]).all():raise ValueError('incomplete refreshed programme')
            self.today=refreshed;self.program_source=source;self.program_loaded=time.monotonic()
            event('programme_refreshed',dict(races=self.today.groupby(['st','r']).ngroups,coverage='source snapshot only'))
        config=json.loads((ROOT/'live/config.json').read_text()); active=config['active_model']=='v4'
        with (primary_connection(Path(config['primary_db'])) if active else conn()) as c:
            table='live_v4_predictions' if active else 'predictions'
            done={(x['st'],x['r']) for x in c.execute(f'SELECT st,r FROM {table} WHERE day=? AND committed_at IS NOT NULL',(str(self.day),))}
        candidates=[]
        for (st,r),group in self.today.sort_values('closed_at').groupby(['st','r'],sort=False):
            deadline=pd.Timestamp(group.closed_at.iloc[0]).to_pydatetime().replace(tzinfo=JST)
            remain=(deadline-now()).total_seconds()
            key=(int(st),int(r))
            if key in done or not 180<remain<=900:continue
            last,n=self.attempts.get(key,(0,0))
            if n>=4 or time.monotonic()-last<180:continue
            self.attempts[key]=(time.monotonic(),n+1)
            try:
                url=f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={r}&jcd={st:02d}&hd={self.day:%Y%m%d}'
                html,source=fetch(url); preview,official_deadline=parse_preview(html.decode('utf-8'),str(self.day),int(r),int(st))
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
                odds=parse_win_odds(html.decode('utf-8'),str(self.day),st,r,live=True)
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

import sys,tempfile,unittest,json,sqlite3,datetime as dt,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'loop/vendor'))
import runner
from sources import rows_from_json,parse_preview,parse_win_odds

class LiveTests(unittest.TestCase):
    def save_at(self,record,db,active,at):
        with patch.object(runner,'now',return_value=at):return runner.save_candidate(record,db,active)
    def test_real_parser_matches_api(self):
        f=ROOT/'live/fixtures';obj=json.loads((f/'v1.txt').read_text());df=rows_from_json(obj)
        rows,deadline=parse_preview((f/'beforeinfo_02.txt').read_text(),'2026-10-15',12)
        for b,row in rows.items():
            truth=df[(df.st==2)&(df.r==12)&(df.boat==b)].iloc[0]
            for k,v in row.items():self.assertEqual(truth[k],v)
        self.assertEqual(deadline,'2026-10-15T16:25:00+09:00')
        self.assertEqual(set(parse_win_odds((f/'oddstf_02.txt').read_text())),set(range(1,7)))
        with self.assertRaises(ValueError):parse_preview('<html/>','2026-10-15',12)
        with self.assertRaises(ValueError):parse_preview((f/'beforeinfo_02.txt').read_text(),'2026-10-16',12,2)
        with self.assertRaises(ValueError):parse_win_odds((f/'oddstf_02.txt').read_text(),'2026-10-15',2,12,live=True)
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
            self.assertTrue(self.save_at(self.record(),db,True,at))
            self.assertFalse(self.save_at(self.record(),db,True,at))
            with sqlite3.connect(db) as c:self.assertTrue(c.execute('SELECT analysis FROM predictions').fetchone()[0].startswith('[v4-live]'))
            with sqlite3.connect(db) as c:
                record=json.loads(c.execute('SELECT record FROM live_v4_predictions').fetchone()[0]);self.assertEqual(record['legacy_prediction']['analysis'],'old')
            (Path(td)/'STOP').touch()
            with self.assertRaises(RuntimeError):self.save_at(self.record(),db,True,at)
    def test_lock_delay_rechecks_time(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            early=dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00');late=dt.datetime.fromisoformat('2026-10-16T12:00:00+09:00')
            with patch.object(runner,'now',side_effect=[early,late]):
                with self.assertRaises(ValueError):runner.save_candidate(self.record(),Path(td)/'unused',False)
            with runner.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM predictions').fetchone()[0],0)
    def make_db(self,td):
        db=Path(td)/'production.db'
        with sqlite3.connect(db) as c:
            c.executescript((ROOT/'live/base/src/boatrace_ai/storage/schema.sql').read_text())
            c.execute("INSERT INTO predictions (race_date,stadium_number,race_number,predicted_order,confidence,recommended_bets,analysis) VALUES ('2026-10-16',2,1,'[2,1,3,4,5,6]',.3,'[]','old')")
        return db
    def test_late_commit_restores_primary(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);calls=[0]
            def clock():
                calls[0]+=1
                return dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00' if calls[0]<=2 else '2026-10-16T12:01:00+09:00')
            with patch.object(runner,'now',side_effect=clock):
                with self.assertRaises(ValueError):runner.save_candidate(self.record(),db,True)
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute('SELECT analysis FROM predictions').fetchone()[0],'old')
                self.assertIsNone(c.execute('SELECT committed_at FROM live_v4_predictions').fetchone()[0])
    def test_crash_between_commits_recovers(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);calls=[0]
            def clock():
                calls[0]+=1
                if calls[0]==3:raise SystemExit('simulated crash after forecast-only commit')
                return dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            with patch.object(runner,'now',side_effect=clock):
                with self.assertRaises(SystemExit):runner.save_candidate(self.record(),db,True)
            with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT analysis FROM predictions').fetchone()[0],'old')
            at=dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            self.assertTrue(self.save_at(self.record(),db,True,at))
            with sqlite3.connect(db) as c:
                r=json.loads(c.execute('SELECT record FROM live_v4_predictions').fetchone()[0])
                self.assertEqual(r['legacy_prediction']['analysis'],'old')
                self.assertEqual(r['operation_status'],'confirmed')
    def test_shadow_does_not_block_primary(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);at=dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            self.assertTrue(self.save_at(self.record(),db,False,at))
            self.assertTrue(self.save_at(self.record(),db,True,at))
    def test_unconfirmed_never_exposed_and_rollback_respects_concurrent_edit(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);calls=[0]
            def clock():
                calls[0]+=1
                if calls[0]==3:
                    with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT analysis FROM predictions').fetchone()[0],'old')
                return dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            with patch.object(runner,'now',side_effect=clock):runner.save_candidate(self.record(),db,True)
            with runner.primary_connection(db) as c:
                record=json.loads(c.execute('SELECT record FROM live_v4_predictions').fetchone()[0])
                c.execute('UPDATE predictions SET confidence=.99')
                self.assertIn('predictions',runner.restore_primary(c,record))
                self.assertEqual(c.execute('SELECT confidence FROM predictions').fetchone()[0],.99)
    def test_legacy_insert_cannot_replace_confirmed_live(self):
        from install_guards import install
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);install(db)
            at=dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            self.save_at(self.record(),db,True,at)
            with sqlite3.connect(db) as c:
                before=c.execute('SELECT id,analysis FROM predictions').fetchone()
                c.execute("INSERT OR REPLACE INTO predictions (race_date,stadium_number,race_number,predicted_order,confidence,recommended_bets,analysis) VALUES ('2026-10-16',2,1,'[2,1,3,4,5,6]',.3,'[]','legacy-late')")
                self.assertEqual(c.execute('SELECT id,analysis FROM predictions').fetchone(),before)
    def test_changed_phase_one_owner_cannot_apply(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);calls=[0]
            def clock():
                calls[0]+=1
                if calls[0]==3:
                    with sqlite3.connect(db) as c:
                        row=json.loads(c.execute('SELECT record FROM live_v4_predictions').fetchone()[0]);row['operation_token']='other-operation'
                        c.execute('UPDATE live_v4_predictions SET record=?',(json.dumps(row),))
                return dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            with patch.object(runner,'now',side_effect=clock):
                with self.assertRaisesRegex(ValueError,'ownership'):runner.save_candidate(self.record(),db,True)
            with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT analysis FROM predictions').fetchone()[0],'old')
if __name__=='__main__':unittest.main()
