#!/usr/bin/env python3
"""boatrace segment-edge gate — FX champion gate の思想を boatrace 台帳に適用。

boatrace_oos.py は train/test 分割で『勝ち場が test でも残るか』を点ROIで見るが、
信頼区間も多重検定補正も無い。本スクリプトはそこに FX で作った規律を足す:

  1. train(前60%)で ROI>=105% の場(min n)を winner として選抜 → screened 母数を記録
  2. test(後40%)で winner 場の per-bet ROI を bootstrap CI で評価
       - 95% CI（素の有意性）
       - Bonferroni 補正 CI（alpha=0.05/screened_n）= 23場を漁った分の多重検定を罰する
  3. arena: winner 場の月次ROIで『プラスの月の割合』を Wilson CI 評価（CI下限>0.5でrobust）
  4. verdict: 補正CI下限>0 かつ arena robust の時だけ『edge_confirmed』

READ-ONLY。実賭けしない。点ROIの誘惑(209%)が変動/選抜バイアスか本物かを決定論的に裁く。
"""
import math
import sqlite3
from collections import defaultdict

import numpy as np

DB = "/Users/apple/.boatrace-ai/boatrace.db"
SEED = 7
NBOOT = 20000
MIN_TRAIN_N = 50
MIN_TEST_N = 20
WIN_ROI = 0.05          # train で +5%(=105%) 以上を winner 候補に


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def roi(stake, pay):
    s = stake.sum()
    return (pay.sum() / s - 1.0) if s else 0.0


def bootstrap_ci(stake, pay, alpha, nboot=NBOOT, seed=SEED):
    n = len(stake)
    if n < MIN_TEST_N:
        return (None, None)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(nboot, n))
    ss = stake[idx].sum(1)
    pp = pay[idx].sum(1)
    rois = pp / ss - 1.0
    return (float(np.percentile(rois, 100 * alpha / 2)),
            float(np.percentile(rois, 100 * (1 - alpha / 2))))


def main():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT race_date, stadium_number, bet_amount, payout FROM virtual_bets "
        "WHERE is_hit IS NOT NULL AND bet_amount>0 AND race_date IS NOT NULL "
        "ORDER BY race_date").fetchall()
    con.close()

    dates = sorted({r[0] for r in rows})
    split = dates[int(len(dates) * 0.6)]
    train = [r for r in rows if r[0] < split]
    test = [r for r in rows if r[0] >= split]
    print(f"TRAIN {train[0][0]}..{split} n={len(train)} | TEST {split}..{test[-1][0]} n={len(test)}")

    # train で場別 ROI → winner 選抜
    tg = defaultdict(list)
    for d, st, b, p in train:
        tg[st].append((b, p))
    screened = [k for k, v in tg.items() if len(v) >= MIN_TRAIN_N]
    winners = [k for k in screened
               if roi(np.array([x[0] for x in tg[k]], float),
                      np.array([x[1] for x in tg[k]], float)) >= WIN_ROI]
    print(f"screened stadiums(n>={MIN_TRAIN_N})={len(screened)}  train-winners(ROI>=105%)={sorted(winners)}")
    alpha_corr = 0.05 / max(1, len(screened))   # Bonferroni
    print(f"多重検定補正: Bonferroni alpha={alpha_corr:.4f} → {100*(1-alpha_corr):.2f}% CI で判定\n")

    # 月次 arena 用に全期間を場別×月で集計
    allg = defaultdict(lambda: defaultdict(list))
    for d, st, b, p in rows:
        allg[st][d[:7]].append((b, p))

    print(f"{'stadium':<9}{'test_n':>7}{'test_ROI':>10}{'95%CI[lo,hi]':>20}"
          f"{'corrCI_lo':>11}{'arena(win/mo)':>14}{'arenaCIlo':>10}{'CONFIRMED':>11}")
    teg = defaultdict(list)
    for d, st, b, p in test:
        teg[st].append((b, p))

    confirmed = []
    for st in sorted(winners):
        bets = teg.get(st, [])
        if len(bets) < MIN_TEST_N:
            print(f"{st:<9}{len(bets):>7}{'(test不足)':>10}")
            continue
        stake = np.array([x[0] for x in bets], float)
        pay = np.array([x[1] for x in bets], float)
        pt = roi(stake, pay)
        lo95, hi95 = bootstrap_ci(stake, pay, 0.05)
        loc, _hic = bootstrap_ci(stake, pay, alpha_corr)
        # arena: 月次
        months = allg[st]
        mo_wins = sum(1 for m, v in months.items()
                      if roi(np.array([x[0] for x in v], float),
                             np.array([x[1] for x in v], float)) > 0)
        mo_tot = len(months)
        a_lo, _a_hi = wilson(mo_wins, mo_tot)
        is_conf = (loc is not None and loc > 0) and (a_lo > 0.5)
        if is_conf:
            confirmed.append(st)
        print(f"{st:<9}{len(bets):>7}{pt*100:>9.1f}%"
              f"{f'[{lo95*100:.0f},{hi95*100:.0f}]':>20}{loc*100:>10.1f}%"
              f"{f'{mo_wins}/{mo_tot}':>14}{a_lo:>10.2f}{('YES' if is_conf else ''):>11}")

    print(f"\n=== 判定 ===")
    print(f"edge_confirmed stadiums = {confirmed or 'なし'}")
    print("confirmed = 補正後CI下限>0(多重検定後も有意) かつ arena月次勝率Wilson下限>0.5(レジーム横断)")
    print("※ paper台帳ベース。実弾はパリミュチュエルでオッズが動くため別途流動性検証が要る(観測のみ)")


if __name__ == "__main__":
    main()
