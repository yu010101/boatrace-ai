import sys,json,time,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'loop/vendor'))
import pandas as pd
import numpy as np
from sources import rows_from_json
from fast_features import Predictor
with sqlite3.connect(f'file:{ROOT}/data/races.db?mode=ro',uri=True) as c: hist=pd.read_sql('select * from boats',c)
hist['date']=pd.to_datetime(hist.date)
with sqlite3.connect(f'file:{ROOT}/data/racers.db?mode=ro',uri=True) as c: kib=pd.read_sql('select * from kibetsu',c)
kib['racer']=pd.to_numeric(kib.toban,errors='coerce');kib['period_to']=pd.to_datetime(kib.period_to)
today=rows_from_json(json.loads((ROOT/'live/fixtures/v1.txt').read_text()))
start=time.monotonic(); pred=Predictor(hist,kib,'2026-10-15',ROOT/'loop/models/202610')
print('ratings_seconds',time.monotonic()-start,flush=True)
fast=pred.build(today); ref=pred.build(today,reference=True)
pd.testing.assert_frame_equal(fast[pred.cols],ref[pred.cols],check_exact=False,rtol=1e-10,atol=1e-10)
a=pred.probabilities(fast);b=pred.probabilities(ref);np.testing.assert_allclose(a,b,rtol=1e-10,atol=1e-10)
report=dict(status='PASS',boats=len(fast),races=fast.race_id.nunique(),columns=len(pred.cols),changed_courses=int((today.pv_course!=today.boat).sum()),second_starts=int((fast.sol_nth_today>1).sum()),max_probability_diff=float(np.max(np.abs(a-b))),seconds=time.monotonic()-start)
(ROOT/'live/feature_parity.json').write_text(json.dumps(report,indent=2)); print(report,flush=True)
