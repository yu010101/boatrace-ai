最終の限定主張の反証: 予測の保存(phase1)が締切前であることと本番反映(phase2)が締切前であることを分離した。後者の絶対保証は主張しない。前回指摘のphase2 commit遅延をテストで再現し、application_before_deadline=false/late_applicationで記録、締切前配信の実績から除外する。forecast_persisted_atはphase1 commit完了を実時計確認した時刻。application_finished_atはphase2 commit完了後に測る時刻。未確認の予測を本番へ出さず、遅延配信を締切前と誤認定しない、という限定主張にコード上の反例があるか。
実行出力:
2026-10-16T12:01:00+09:00 late_application 2026-10-16/2/1; forecast was saved earlier, delivery was late
...........
----------------------------------------------------------------------
Ran 11 tests in 0.367s

OK

def deadline_ok(deadline,observations,at=None):
    at=at or now();end=dt.datetime.fromisoformat(deadline)
    return at.tzinfo is not None and at.date()==end.date() and at<end-dt.timedelta(seconds=60) and all(dt.datetime.fromisoformat(x['finished'])<end and dt.datetime.fromisoformat(x['finished'])<=at for x in observations)

def primary_connection(path):
    if not path.exists(): raise FileNotFoundError(path)
    c=sqlite3.connect(path,timeout=20);c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS live_v4_predictions(day TEXT,st INTEGER,r INTEGER,deadline TEXT,forecast_persisted_at TEXT,record TEXT,PRIMARY KEY(day,st,r))')
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
        old_record=c.execute(f'SELECT forecast_persisted_at FROM {table} WHERE day=? AND st=? AND r=?',(day,st,r)).fetchone()
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
        owned=c.execute(f'SELECT forecast_persisted_at,record FROM {table} WHERE day=? AND st=? AND r=?',(day,st,r)).fetchone()
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
        c.execute(f'UPDATE {table} SET forecast_persisted_at=?,record=? WHERE day=? AND st=? AND r=?',(persisted.isoformat(),json.dumps(record,ensure_ascii=False),day,st,r));c.commit()
        applied=now()
        record['application_finished_at']=applied.isoformat()
        record['application_before_deadline']=applied<dt.datetime.fromisoformat(record['deadline'])
        c.execute(f'UPDATE {table} SET record=? WHERE day=? AND st=? AND r=?',(json.dumps(record,ensure_ascii=False),day,st,r));c.commit()
        if not record['application_before_deadline']:event('late_application',f'{day}/{st}/{r}; forecast was saved earlier, delivery was late')
        return True
    except Exception:c.rollback();raise
    finally:c.close()


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
                self.assertIsNone(c.execute('SELECT forecast_persisted_at FROM live_v4_predictions').fetchone()[0])
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
    def test_application_delay_is_not_mislabeled_predeadline_delivery(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);calls=[0]
            def clock():
                calls[0]+=1
                return dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00' if calls[0]<=5 else '2026-10-16T12:01:00+09:00')
            with patch.object(runner,'now',side_effect=clock):runner.save_candidate(self.record(),db,True)
            with sqlite3.connect(db) as c:
                rec=json.loads(c.execute('SELECT record FROM live_v4_predictions').fetchone()[0])
                self.assertTrue(rec['pre_deadline_verified'])
                self.assertFalse(rec['application_before_deadline'])
                self.assertEqual(rec['forecast_persisted_at'],'2026-10-16T11:57:00+09:00')
if __name__=='__main__':unittest.main()
