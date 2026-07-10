#!/usr/bin/env python3
"""Backward winner-segment discovery for boatrace-ai (the PTCG 'learn from winners' pattern).
READ-ONLY analysis of settled virtual_bets: which segments (stadium / grade / odds-band / EV-band)
were actually ROI-POSITIVE? The current EV>1.0 gate doesn't beat takeout — find segments that DO.
Does NOT enable real betting. Output = a candidate 'winning filter' for human review.
"""
import sqlite3
DB = "/Users/apple/.boatrace-ai/boatrace.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
c = con.cursor()

rows = c.execute("""SELECT stadium_number, race_number, bet_type, grade, bet_amount, payout, is_hit,
                           model_prob, market_odds, ev
                    FROM virtual_bets WHERE is_hit IS NOT NULL AND bet_amount>0""").fetchall()
N = len(rows)
tot_stake = sum(r["bet_amount"] for r in rows)
tot_pay = sum(r["payout"] for r in rows)
print(f"settled bets: {N} | overall ROI: {tot_pay*100.0/tot_stake:.1f}% (takeout floor ~75-85%)")
print(f"(baseline: a profitable segment must clear 100%+ ROI consistently)\n")

def roi(subset):
    s = sum(r["bet_amount"] for r in subset); p = sum(r["payout"] for r in subset)
    return (p*100.0/s if s else 0), len(subset), s

def report(name, keyfn, minn=80):
    from collections import defaultdict
    g = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is not None: g[k].append(r)
    out = []
    for k, sub in g.items():
        r_, n_, s_ = roi(sub)
        if n_ >= minn: out.append((r_, n_, k))
    out.sort(reverse=True)
    print(f"=== {name} (ROI%, n) — segments with n>={minn} ===")
    for r_, n_, k in out[:6]:
        flag = " <<< PROFITABLE" if r_ >= 100 else ""
        print(f"  {r_:6.1f}%  n={n_:<5} {k}{flag}")
    if out and out[0][0] < 100:
        print(f"  (best segment {out[0][0]:.1f}% still < 100% — no profitable cluster here)")
    print()

report("by stadium", lambda r: f"stadium{r['stadium_number']}")
report("by grade", lambda r: r["grade"] or "(none)")
report("by bet_type", lambda r: r["bet_type"], minn=50)
def odds_band(r):
    o = r["market_odds"]
    if o is None: return None
    for lo,hi in [(1,5),(5,10),(10,20),(20,50),(50,100),(100,1e9)]:
        if lo<=o<hi: return f"odds {lo}-{hi if hi<1e9 else '+'}"
report("by odds band", odds_band)
def ev_band(r):
    e = r["ev"]
    if e is None: return None
    for lo,hi in [(1.0,1.1),(1.1,1.3),(1.3,1.6),(1.6,2.0),(2.0,1e9)]:
        if lo<=e<hi: return f"EV {lo}-{hi if hi<1e9 else '+'}"
report("by EV band", ev_band)

# combined best: stadium x odds-band, looking for any pocket clearing 100%
from collections import defaultdict
g = defaultdict(list)
for r in rows:
    ob = odds_band(r)
    if ob: g[(f"stadium{r['stadium_number']}", ob)].append(r)
combo = []
for k, sub in g.items():
    r_, n_, s_ = roi(sub)
    if n_ >= 40: combo.append((r_, n_, k))
combo.sort(reverse=True)
print("=== best stadium x odds pockets (n>=40) ===")
for r_, n_, k in combo[:8]:
    print(f"  {r_:6.1f}%  n={n_:<4} {k}{'  <<<' if r_>=100 else ''}")
con.close()
