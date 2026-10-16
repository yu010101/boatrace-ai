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
    def test_stale_delivery_flag_cannot_survive_crash(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'STATE',Path(td)):
            db=self.make_db(td);calls=[0];record=self.record()
            record.update(application_before_deadline=True,application_finished_at='old')
            def clock():
                calls[0]+=1
                if calls[0]==6:raise SystemExit('post commit crash')
                return dt.datetime.fromisoformat('2026-10-16T11:57:00+09:00')
            with patch.object(runner,'now',side_effect=clock):
                with self.assertRaises(SystemExit):runner.save_candidate(record,db,True)
            with sqlite3.connect(db) as c:
                rec=json.loads(c.execute('SELECT record FROM live_v4_predictions').fetchone()[0])
                self.assertNotIn('application_before_deadline',rec)
                self.assertNotIn('application_finished_at',rec)
if __name__=='__main__':unittest.main()
