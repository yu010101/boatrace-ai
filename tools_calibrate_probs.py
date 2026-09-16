#!/usr/bin/env python3
"""モデル確率の較正を測る(読み取り専用・本番には触れない)。
前半期間で較正係数を作り、後半期間で検証する。自分で同じ罠(in-sample)を踏まないため時系列で分割する。
"""
import sqlite3, math, sys
DB="/Users/radineer01/.boatrace-ai/boatrace.db"
SPLIT="2026-07-01"   # 前半=学習 / 後半=検証
def load(bt):
    q="""select race_date, model_prob p, market_odds o, is_hit h, bet_amount a, payout pay
         from virtual_bets where bet_type=? and is_hit is not null
           and model_prob is not null and market_odds is not null"""
    return sqlite3.connect(f"file:{DB}?mode=ro",uri=True).execute(q,(bt,)).fetchall()
def logloss(rows,f):
    s=n=0
    for _,p,o,h,a,pay in rows:
        q=min(max(f(p),1e-6),1-1e-6); s+= -(h*math.log(q)+(1-h)*math.log(1-q)); n+=1
    return s/max(n,1)
def fit_scale(rows):
    """p_cal = c*p の c を、実測的中数/期待的中数 で求める(モーメント法)"""
    exp=sum(r[1] for r in rows); act=sum(r[3] for r in rows)
    return act/exp if exp>0 else 1.0
def roi(rows):
    a=sum(r[4] for r in rows); pay=sum(r[5] for r in rows)
    return (100.0*(pay-a)/a if a else 0.0), len(rows), a
for bt in ("2連単","単勝"):
    rows=load(bt)
    tr=[r for r in rows if r[0]<SPLIT]; te=[r for r in rows if r[0]>=SPLIT]
    if not tr or not te: print(bt,"データ不足"); continue
    c=fit_scale(tr)
    print(f"== {bt}  学習{len(tr)}件 / 検証{len(te)}件")
    print(f"   前半で測った較正係数 c = {c:.3f}  (1.0未満=モデルが過大)")
    print(f"   後半の実測 c        = {fit_scale(te):.3f}   ← 前半と近ければ較正は安定")
    print(f"   logloss 検証: 較正なし {logloss(te,lambda p:p):.4f} / 較正あり {logloss(te,lambda p:c*p):.4f}")
    r_all=roi(te); print(f"   後半 全ベット: ROI {r_all[0]:+.1f}%  n={r_all[1]}  投下¥{r_all[2]:,}")
    for th in (0.0,0.1,0.2,0.3):
        kept=[r for r in te if (c*r[1])*r[2]-1 > th]
        if kept:
            rr=roi(kept); print(f"   較正後EV>{th:.1f} だけ賭けた場合: ROI {rr[0]:+.1f}%  n={rr[1]}  投下¥{rr[2]:,}")
        else:
            print(f"   較正後EV>{th:.1f}: 該当なし(=1本も賭けない)")
