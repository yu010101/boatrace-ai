# live_v4 の型エラー再現: 直前情報を空欄にした当日表へ1レース分だけ値を入れて build する
import sys, json, sqlite3
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(R/'loop/vendor'), str(R/'live')]
import pandas as pd, numpy as np
from sources import rows_from_json, parse_preview
from fast_features import Predictor
f = R/'live/fixtures'
obj = json.loads((f/'v1.txt').read_text())
day = '2026-10-15'
with sqlite3.connect(f'file:{R}/data/races.db?mode=ro', uri=True) as c: hist = pd.read_sql('select * from boats', c)
hist.date = pd.to_datetime(hist.date)
with sqlite3.connect(f'file:{R}/data/racers.db?mode=ro', uri=True) as c: kib = pd.read_sql('select * from kibetsu', c)
kib['racer'] = pd.to_numeric(kib.toban, errors='coerce'); kib.period_to = pd.to_datetime(kib.period_to)
P = Predictor(hist, kib, day, R/'loop/models/202610')
today = rows_from_json(obj, mask=True)
rows, _ = parse_preview((f/'beforeinfo_02.txt').read_text(), day, 12, 2)
for b, v in rows.items():
    m = (today.st == 2) & (today.r == 12) & (today.boat == b)
    for col, val in v.items(): today.loc[m, col] = val
print('pv_wind_dir dtype', today.pv_wind_dir.dtype)
fr = P.build(today); fr['p'] = P.probabilities(fr)
live = fr[(fr.st == 2) & (fr.r == 12)].sort_values('boat')[['boat', 'p']]
# 比較: 当日結果だけ消した完全な表（parity と同じ入力）で同じレースを計算
full = rows_from_json(obj); full[['place', 'technique', 'rs_course', 'rs_st']] = np.nan
fr2 = P.build(full); fr2['p'] = P.probabilities(fr2)
ref = fr2[(fr2.st == 2) & (fr2.r == 12)].sort_values('boat')[['boat', 'p']]
print(live.p.round(4).tolist()); print(ref.p.round(4).tolist())
print('max diff', float(np.abs(live.p.values - ref.p.values).max()))
