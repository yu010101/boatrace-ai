#!/usr/bin/env python3
"""Out-of-sample validation of the winning segments (PTCG lesson: in-sample edge may be a leak).
Split settled bets by date into TRAIN (earlier 60%) and TEST (later 40%).
Find ROI>=105% stadium-segments in TRAIN, then check if they STILL clear 100% in TEST.
If they collapse on TEST -> overfit (no real edge). READ-ONLY. No real betting.
"""
import sqlite3
from collections import defaultdict
DB = "/Users/apple/.boatrace-ai/boatrace.db"
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
rows = con.execute("""SELECT race_date, stadium_number, market_odds, bet_amount, payout
                      FROM virtual_bets WHERE is_hit IS NOT NULL AND bet_amount>0 AND race_date IS NOT NULL
                      ORDER BY race_date""").fetchall()
con.close()
dates = sorted(set(r["race_date"] for r in rows))
split = dates[int(len(dates)*0.6)]
train = [r for r in rows if r["race_date"] < split]
test  = [r for r in rows if r["race_date"] >= split]
print(f"TRAIN {train[0]['race_date']}..{split} n={len(train)} | TEST {split}..{test[-1]['race_date']} n={len(test)}\n")

def roi(sub):
    s=sum(r["bet_amount"] for r in sub); p=sum(r["payout"] for r in sub)
    return (p*100.0/s if s else 0), len(sub)

def seg(rs, keyfn, minn):
    g=defaultdict(list)
    for r in rs:
        k=keyfn(r)
        if k is not None: g[k].append(r)
    return {k:roi(v) for k,v in g.items() if len(v)>=minn}

# 1) stadium-level edge persistence
key=lambda r:r["stadium_number"]
tr=seg(train,key,50); te=seg(test,key,30)
winners=[k for k,(r,n) in tr.items() if r>=105]
print("=== stadiums that were ROI>=105% in TRAIN — do they hold in TEST? ===")
hold=0
for k in sorted(winners, key=lambda k:-tr[k][0]):
    tr_r,tr_n=tr[k]; te_r,te_n=te.get(k,(None,0))
    if te_r is None:
        print(f"  stadium{k}: TRAIN {tr_r:.0f}% (n{tr_n}) | TEST n/a")
    else:
        ok = te_r>=100
        hold += ok
        print(f"  stadium{k}: TRAIN {tr_r:.0f}% (n{tr_n}) -> TEST {te_r:.0f}% (n{te_n}) {'HOLDS' if ok else 'COLLAPSES'}")
print(f"\nverdict: {hold}/{len(winners)} train-winning stadiums still profitable out-of-sample")
# overall TEST roi of betting ALL train-winners vs everything
alltest_r,_=roi(test)
wsub=[r for r in test if r["stadium_number"] in winners]
wr,wn=roi(wsub) if wsub else (0,0)
print(f"TEST ROI: bet-all={alltest_r:.1f}% | bet-only-train-winners={wr:.1f}% (n={wn})")
print("\nNOTE: in-sample winners that COLLAPSE out-of-sample = overfit, NOT a real edge. Observation only.")
