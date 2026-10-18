import unittest,json,tempfile,hashlib
from pathlib import Path
from audit import settle,verify
class AuditTest(unittest.TestCase):
 def setUp(self):
  self.rec={'probabilities':dict(zip('123456',[.5,.1,.1,.1,.1,.1])),'legacy_prediction':{'predicted_order':'[2,1,3,4,5,6]'}}
  self.result={'actual_order':'[1,2,3,4,5,6]','payouts_json':json.dumps({'win':[{'combination':'1','payout':200}]})}
 def test_pending_not_loss(self):self.assertEqual(settle(self.rec,None),{'status':'pending'})
 def test_matched_comparison(self):
  s=settle(self.rec,self.result);self.assertEqual((s['return_yen'],s['legacy_return_yen']),(200,0))
 def test_missing_payout(self):
  self.result['payouts_json']='{}';self.assertEqual(settle(self.rec,self.result)['status'],'review_required')
 def test_refund_review(self):
  self.result['actual_order']='[1,2,3,4,5]';self.assertEqual(settle(self.rec,self.result)['status'],'review_required')
 def test_null_payout(self):
  self.result['payouts_json']='null';self.assertEqual(settle(self.rec,self.result)['status'],'review_required')
 def test_refund_flag(self):
  self.result['payouts_json']=json.dumps({'win':[{'combination':'1','payout':200}],'refunds':[2]});self.assertEqual(settle(self.rec,self.result)['status'],'review_required')
 def test_boolean_finish(self):
  self.result['actual_order']='[true,2,3,4,5,6]';self.assertEqual(settle(self.rec,self.result)['status'],'review_required')
 def test_bad_legacy(self):
  self.rec['legacy_prediction']=[1];s=settle(self.rec,self.result);self.assertEqual(s['status'],'settled');self.assertIsNone(s['legacy_boat'])
 def test_invalid_payout(self):
  self.result['payouts_json']='{"win":[{"combination":"2","payout":200}]}';self.assertEqual(settle(self.rec,self.result)['status'],'review_required')
 def test_evidence_and_tampering(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'raw';p.write_bytes(b'actual')
   source={'path':str(p),'sha256':hashlib.sha256(b'actual').hexdigest(),'started':'2026-10-16T09:55:00+09:00','finished':'2026-10-16T09:55:01+09:00'}
   x=dict(self.rec,day='2026-10-16',st=1,r=1,deadline='2026-10-16T10:00:00+09:00',forecast_persisted_at='2026-10-16T09:56:00+09:00',pre_deadline_verified=True,win_odds={b:2 for b in '123456'},sources=[dict(source,url=u,request_id=i) for i,u in enumerate(['https://boatraceopenapi.github.io/api/v1/2026/20261016.json','https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=1&jcd=01&hd=20261016','https://www.boatrace.jp/owpc/pc/race/oddstf?rno=1&jcd=01&hd=20261016'])],application_before_deadline=True,application_finished_at='2026-10-16T09:56:01+09:00')
   row={k:x[k] for k in ['day','st','r','deadline','forecast_persisted_at']};row['record']=json.dumps(x)
   self.assertTrue(verify(row)[1])
   y=dict(x,win_odds={b:2 for b in '12346'},win_odds_unbet=['5']);ok=dict(row,record=json.dumps(y));self.assertTrue(verify(ok)[1])
   y=dict(x,win_odds={b:2 for b in '12346'});self.assertIsNone(verify(dict(row,record=json.dumps(y)))[0])
   bad=dict(row,day='2026-10-15');badx=dict(x,day='2026-10-15');bad['record']=json.dumps(badx);self.assertIsNone(verify(bad)[0])
   p.write_bytes(b'changed');self.assertIsNone(verify(row)[0])
   p.write_bytes(b'actual');x['forecast_persisted_at']='2026-10-16T10:01:00+09:00';row['forecast_persisted_at']=x['forecast_persisted_at'];row['record']=json.dumps(x);self.assertIsNone(verify(row)[0])
if __name__=='__main__':unittest.main()
