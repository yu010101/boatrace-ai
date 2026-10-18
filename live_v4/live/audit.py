"""Read-only evidence audit and fixed 100-yen win-bet simulation. No orders."""
import argparse,datetime as dt,hashlib,json,math,sqlite3
from pathlib import Path
POLICY={'id':'v4-top1-win-flat100-v1','stake_yen':100,'selection':'highest model probability; lower boat number breaks ties','eligible':'verified pre-deadline forecast, six valid finishers and official win payout; other results require review','odds_usage':'record only; official final payout determines settlement','purchase':False}
def stamp(value):
    v=dt.datetime.fromisoformat(value)
    if v.tzinfo is None:raise ValueError('naive time')
    return v

def verify(row):
    errors=[]
    try:
        x=json.loads(row['record']);end=stamp(row['deadline']);saved=stamp(row['forecast_persisted_at'])
        assert x['pre_deadline_verified'] is True
        assert (x['day'],x['st'],x['r'])==(row['day'],row['st'],row['r'])
        assert x['deadline']==row['deadline'] and x['forecast_persisted_at']==row['forecast_persisted_at']
        assert saved.date()==end.date() and saved<end-dt.timedelta(seconds=60)
        probs=x['probabilities'];odds=x['win_odds']
        unbet=x.get('win_odds_unbet',[])
        assert set(probs)==set('123456') and odds and not set(odds)&set(unbet) and set(odds)|set(unbet)==set('123456')
        assert all(isinstance(v,(int,float)) and math.isfinite(v) and 0<v<1 for v in probs.values())
        assert abs(sum(probs.values())-1)<1e-8
        assert all(isinstance(v,(int,float)) and math.isfinite(v) and v>=1 for v in odds.values())
        assert len(x['sources'])==3
        day=dt.date.fromisoformat(x['day']);st=x['st'];r=x['r']
        assert end.date()==day and saved.date()==day
        expected={f'https://boatraceopenapi.github.io/api/v1/{day.year}/{day:%Y%m%d}.json',f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={r}&jcd={st:02d}&hd={day:%Y%m%d}',f'https://www.boatrace.jp/owpc/pc/race/oddstf?rno={r}&jcd={st:02d}&hd={day:%Y%m%d}'}
        assert {v['url'] for v in x['sources']}==expected
        assert len({v['request_id'] for v in x['sources']})==3
        for s in x['sources']:
            assert stamp(s['started'])<=stamp(s['finished'])<=saved
            assert stamp(s['finished'])<end
            assert hashlib.sha256(Path(s['path']).read_bytes()).hexdigest()==s['sha256']
        delivered=x.get('application_before_deadline') is True and saved<=stamp(x['application_finished_at'])<end
        return x,delivered,errors
    except (AssertionError,ValueError,TypeError,KeyError,OSError,AttributeError,IndexError) as e:
        errors.append(type(e).__name__+': '+str(e));return None,False,errors

def settle(record,result):
    if result is None:return {'status':'pending'}
    try:
        order=json.loads(result['actual_order']);raw=json.loads(result['payouts_json'])
        if not isinstance(raw,dict):return {'status':'review_required','reason':'invalid payout container'}
        if any(raw.get(k) for k in ['refund','refunds','cancelled','canceled']):return {'status':'review_required','reason':'refund/cancellation flag'}
        payout=raw['win']
        if not isinstance(order,list) or not all(type(v) is int for v in order) or sorted(order)!=[1,2,3,4,5,6]:return {'status':'review_required','reason':'nonstandard finish/refund/cancellation'}
        if len(payout)!=1:return {'status':'review_required','reason':'missing/ambiguous win payout'}
        winner=int(payout[0]['combination']);amount=payout[0]['payout']
        if winner!=order[0] or isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount<100:
            return {'status':'review_required','reason':'invalid win payout'}
        boat=min(range(1,7),key=lambda b:(-record['probabilities'][str(b)],b))
        legacy=record.get('legacy_prediction') or {}
        try:old=json.loads(legacy.get('predicted_order') or 'null') if isinstance(legacy,dict) else None
        except (TypeError,ValueError):old=None
        old_boat=old[0] if isinstance(old,list) and len(old)==6 and all(type(v) is int for v in old) and sorted(old)==[1,2,3,4,5,6] else None
        return {'status':'settled','boat':boat,'hit':boat==winner,'stake_yen':100,'return_yen':amount if boat==winner else 0,
          'legacy_boat':old_boat,'legacy_hit':old_boat==winner if old_boat else None,'legacy_return_yen':(amount if old_boat==winner else 0) if old_boat else None}
    except (ValueError,TypeError,KeyError,AttributeError,IndexError):return {'status':'review_required','reason':'malformed result'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);ap.add_argument('--state',required=True);args=ap.parse_args()
    c=sqlite3.connect(Path(args.db).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    report={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'policy':POLICY,'limitations':['Internal wall-clock records and file hashes only; not independent timestamp attestation.','Simulation covers standard six-finisher results only; unknown/refund/cancelled rows excluded and counted.','ROI of settled subset only; paired comparison covers rows with both predictions, not all scheduled races.'],'records':[]}
    for row in c.execute('SELECT * FROM live_v4_predictions ORDER BY day,st,r'):
        x,delivered,errors=verify(row)
        result=c.execute('SELECT actual_order,payouts_json FROM results WHERE race_date=? AND stadium_number=? AND race_number=?',(row['day'],row['st'],row['r'])).fetchone()
        report['records'].append({'day':row['day'],'st':row['st'],'r':row['r'],'forecast_verified':x is not None,'delivered_before_deadline':delivered,'errors':errors,**(settle(x,result) if x else {'status':'invalid_evidence'})})
    c.close();rows=report['records'];done=[x for x in rows if x['status']=='settled'];paired=[x for x in done if x['legacy_boat'] is not None]
    report['summary']={'total':len(rows),'verified':sum(x['forecast_verified'] for x in rows),'delivered':sum(x['delivered_before_deadline'] for x in rows),'settled':len(done),'pending':sum(x['status']=='pending' for x in rows),'review_required':sum(x['status']=='review_required' for x in rows),'invalid_evidence':sum(x['status']=='invalid_evidence' for x in rows),'stake_yen':100*len(done),'return_yen':sum(x['return_yen'] for x in done),'roi':sum(x['return_yen'] for x in done)/(100*len(done)) if done else None,'paired_races':len(paired),'paired_v4_hits':sum(x['hit'] for x in paired),'paired_legacy_hits':sum(x['legacy_hit'] for x in paired),'paired_v4_returns':sum(x['return_yen'] for x in paired),'paired_legacy_returns':sum(x['legacy_return_yen'] for x in paired)}
    state=Path(args.state);report['heartbeat']=json.loads((state/'heartbeat.json').read_text())
    with sqlite3.connect((state/'live.db').resolve().as_uri()+'?mode=ro',uri=True) as s:
        report['events']=s.execute('select created_at,kind,detail from events order by rowid desc limit 10').fetchall()
        report['requests']=s.execute('select day,status,count(*) from requests group by day,status').fetchall()
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
