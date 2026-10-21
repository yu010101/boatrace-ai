"""月ごとのモデルだけを先に作る（2026-10-21 本人OK「11/1 のモデル期限の対応」）。

本番（M4 live_v4/live/runner.py）は loop/models/YYYYMM を読む。daily.py は「前日の答え合わせ」のついでに
その月のモデルを作るため、月初の朝には間に合わない。ここでは daily.py と同じ部品・同じ手順で、
学習＝前々月末まで、調整＝前月、のモデルを作り、daily.py と同じ形の manifest.json を書く
（後の答え合わせで daily.py が meta['code'] を照合するので、code の中身も daily.py と同じにする）。

  python loop/build_month.py --month 2026-11            # loop/models/202611 を作る（前月末までの結果がそろってから）
  python loop/build_month.py --month 2026-10 --out /tmp/x  # 検算: 既存の 202610 とハッシュが一致するか
"""
import argparse, datetime as dt, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily as D  # noqa: E402  daily.py の定数と関数をそのまま使う（daily.py は書き換えない）
import numpy as np, pandas as pd, lightgbm as lgb  # noqa: E402
from scipy.optimize import minimize_scalar  # noqa: E402


def build(month: dt.date, out_root: Path, fetch: bool) -> Path:
    month_ts = pd.Timestamp(month)
    last = month - dt.timedelta(days=1)  # 前月末。daily.py の prepare は day 以前の行を返す
    raw, dbhash = D.prepare(last, fetch)
    tune_start = month_ts - pd.DateOffset(months=1)
    if raw[raw.date >= tune_start].empty:
        raise ValueError('前月のデータが無い')
    lastday = raw[raw.date == pd.Timestamp(last)]
    if lastday.empty or lastday.place.isna().any():
        raise ValueError(f'{last} の結果がそろっていない。そろってから作る')
    kib = D.load_kibetsu()
    df, F = D.build4(raw, kib)
    cols = list(dict.fromkeys(F['base'] + [c for g in D.GROUPS for c in F[g]]))
    assert not set(cols) & set(D.RESULT_COLS)
    df = df.sort_values(['date', 'st', 'r', 'boat']).reset_index(drop=True)
    good = df.groupby('race_id').win.transform('sum') == 1
    tr = df[(df.date < tune_start) & good]
    tu = df[(df.date >= tune_start) & (df.date < month_ts) & good]
    assert tr.date.max() < tu.date.min()
    code = {p.name: D.sha(p) for p in (D.ROOT / 'model_exp').glob('features*.py')}
    code['daily.py'] = D.sha(Path(D.__file__))
    code['build_races.py'] = D.sha(D.ROOT / 'scripts/build_races.py')
    code['racers.db'] = D.sha(D.ROOT / 'data/racers.db')
    import trueskill
    versions = {k: v.__version__ for k, v in [('numpy', np), ('pandas', pd), ('lightgbm', lgb), ('trueskill', trueskill)]}
    modeldir = out_root / f'{month:%Y%m}'
    if (modeldir / 'manifest.json').exists():
        raise FileExistsError(f'{modeldir} はもうある。上書きしない')
    modeldir.mkdir(parents=True, exist_ok=True)
    a = np.zeros(len(tu))
    for seed in D.SEEDS:
        print('train', seed, flush=True)
        train = lgb.Dataset(tr[cols], tr.win, categorical_feature=[c for c in ['st', 'branch'] if c in cols])
        tune = lgb.Dataset(tu[cols], tu.win, reference=train)
        m = lgb.train(dict(D.PARAMS, seed=seed), train, 4000, valid_sets=[tune], callbacks=[lgb.early_stopping(100, verbose=False)])
        a += m.predict(tu[cols]) / len(D.SEEDS)
        m.save_model(str(modeldir / f'{seed}.txt'))
    a = D.norm(a, tu)
    winner = (tu.win == 1).values
    T = float(minimize_scalar(lambda t: -np.log(D.calibrated(a, tu, t)[winner]).mean(), bounds=(.3, 3.), method='bounded').x)
    meta = dict(columns=cols, code=code, versions=versions, T=T, seeds=D.SEEDS, params=D.PARAMS,
                train_max=str(tr.date.max()), tune_min=str(tu.date.min()), tune_max=str(tu.date.max()),
                train_races=tr.race_id.nunique(), tune_races=tu.race_id.nunique(), input_db_sha256=dbhash,
                models={f'{s}.txt': D.sha(modeldir / f'{s}.txt') for s in D.SEEDS})
    D.save_json(modeldir / 'manifest.json', meta)
    print(json.dumps({k: meta[k] for k in ['T', 'train_max', 'tune_min', 'tune_max', 'train_races', 'tune_races', 'models']}, ensure_ascii=False, default=str), flush=True)
    return modeldir


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--month', required=True, help='YYYY-MM（作るモデルの月）')
    ap.add_argument('--out', default=str(D.OUT / 'models'))
    ap.add_argument('--fetch', action='store_true', help='前月末の Open API を取り直す')
    args = ap.parse_args()
    month = dt.date.fromisoformat(args.month + '-01')
    build(month, Path(args.out), args.fetch)
