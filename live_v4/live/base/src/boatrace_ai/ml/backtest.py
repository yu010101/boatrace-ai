"""Backtest EV-based betting strategy against historical data.

Uses post-race payouts from the DB as odds proxy (conservative estimate,
since actual pre-race odds are higher than post-race payouts per 100 yen).
"""

from __future__ import annotations

import json
import logging

from boatrace_ai.ml.bets import DEFAULT_BANKROLL, MIN_EV
from boatrace_ai.storage.database import get_predictions_with_results

log = logging.getLogger(__name__)


def _payouts_to_odds(payouts_json: str) -> dict:
    """Convert post-race payouts JSON to odds-like dict.

    Payouts are per 100 yen, so they already represent decimal odds
    (e.g., payout=1500 means 15.0x return on 100 yen = odds of 15.0).
    """
    try:
        payouts = json.loads(payouts_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    odds: dict[str, dict] = {
        "win": {},
        "exacta": {},
        "quinella": {},
        "trifecta": {},
        "trio": {},
    }

    # Win odds
    for entry in payouts.get("win", []):
        combo = entry.get("combination", "")
        payout = entry.get("payout", 0)
        if combo and payout > 0:
            # payout per 100 yen = decimal odds
            odds["win"][int(combo)] = payout / 100.0

    # Exacta
    for entry in payouts.get("exacta", []):
        combo = entry.get("combination", "")
        payout = entry.get("payout", 0)
        if combo and payout > 0:
            odds["exacta"][combo] = payout / 100.0

    # Quinella
    for entry in payouts.get("quinella", []):
        combo = entry.get("combination", "")
        payout = entry.get("payout", 0)
        if combo and payout > 0:
            odds["quinella"][combo] = payout / 100.0

    # Trifecta
    for entry in payouts.get("trifecta", []):
        combo = entry.get("combination", "")
        payout = entry.get("payout", 0)
        if combo and payout > 0:
            odds["trifecta"][combo] = payout / 100.0

    # Trio
    for entry in payouts.get("trio", []):
        combo = entry.get("combination", "")
        payout = entry.get("payout", 0)
        if combo and payout > 0:
            odds["trio"][combo] = payout / 100.0

    return odds


def _simulate_old_strategy(
    predicted_order: list[int],
    probs: list[float],
    payouts_json: str,
) -> dict:
    """Simulate the old probability-threshold strategy with fixed ¥1,000 bets."""
    from boatrace_ai.ml.bets import generate_bets
    from boatrace_ai.tracking.roi import match_bet_to_payout, parse_bet_string

    bets = generate_bets(predicted_order, probs)
    total_invested = len(bets) * 1000
    total_payout = 0
    hits = 0

    for bet_str in bets:
        parsed = parse_bet_string(bet_str)
        if parsed is None:
            continue
        bet_type, combination = parsed
        payout = match_bet_to_payout(bet_type, combination, payouts_json)
        if payout > 0:
            total_payout += payout
            hits += 1

    return {
        "total_bets": len(bets),
        "total_invested": total_invested,
        "total_payout": total_payout,
        "hits": hits,
    }


def _simulate_ev_strategy(
    predicted_order: list[int],
    probs_dict: dict[int, float],
    payouts_json: str,
    min_ev: float = MIN_EV,
    kelly_fraction: float = 0.25,
    bankroll: int = DEFAULT_BANKROLL,
) -> dict:
    """Simulate the new EV-based strategy using post-race payouts as odds proxy."""
    from boatrace_ai.ml.bets import generate_bets_ev
    from boatrace_ai.tracking.roi import match_bet_to_payout

    odds = _payouts_to_odds(payouts_json)
    if not odds.get("win"):
        return {"total_bets": 0, "total_invested": 0, "total_payout": 0, "hits": 0}

    ev_bets = generate_bets_ev(
        predicted_order,
        probs_dict,
        odds_win=odds.get("win"),
        odds_exacta=odds.get("exacta"),
        odds_quinella=odds.get("quinella"),
        odds_trifecta=odds.get("trifecta"),
        odds_trio=odds.get("trio"),
        bankroll=bankroll,
        min_ev=min_ev,
        kelly_fraction=kelly_fraction,
    )

    total_invested = sum(b.bet_amount for b in ev_bets)
    total_payout = 0
    hits = 0

    for bet in ev_bets:
        payout = match_bet_to_payout(
            bet.bet_type, bet.combination, payouts_json,
            bet_amount=bet.bet_amount,
        )
        if payout > 0:
            total_payout += payout
            hits += 1

    return {
        "total_bets": len(ev_bets),
        "total_invested": total_invested,
        "total_payout": total_payout,
        "hits": hits,
    }


def run_backtest(
    start_date: str,
    end_date: str | None = None,
    min_ev: float = MIN_EV,
    kelly_fraction: float = 0.25,
) -> dict:
    """Run backtest comparing old vs new betting strategy.

    Uses predictions already in the DB along with actual results/payouts.

    Returns:
        dict with "old" and "new" keys, each containing:
        total_bets, total_invested, total_payout, profit, roi, hit_count, hit_rate
    """
    rows = get_predictions_with_results(start_date, end_date)

    old_totals = {"total_bets": 0, "total_invested": 0, "total_payout": 0, "hits": 0}
    new_totals = {"total_bets": 0, "total_invested": 0, "total_payout": 0, "hits": 0}

    for row in rows:
        try:
            predicted_order = json.loads(row["predicted_order"])
        except (json.JSONDecodeError, TypeError):
            continue

        if len(predicted_order) < 3:
            continue

        payouts_json = row.get("payouts_json")
        if not payouts_json:
            continue

        # Build probability dict: assume uniform-ish based on order
        # Since we don't store raw probs in predictions table, estimate from confidence
        confidence = row.get("confidence", 0.3)
        n = len(predicted_order)
        # Generate decreasing probs that sum to 1
        probs_list = []
        for rank in range(n):
            # Exponential decay from confidence
            p = confidence * (0.7 ** rank)
            probs_list.append(p)
        total_p = sum(probs_list)
        probs_list = [p / total_p for p in probs_list]

        probs_dict = {predicted_order[i]: probs_list[i] for i in range(n)}

        # Old strategy
        old_result = _simulate_old_strategy(predicted_order, probs_list, payouts_json)
        for key in old_totals:
            old_totals[key] += old_result[key]

        # New strategy
        new_result = _simulate_ev_strategy(
            predicted_order, probs_dict, payouts_json,
            min_ev=min_ev, kelly_fraction=kelly_fraction,
        )
        for key in new_totals:
            new_totals[key] += new_result[key]

    def _summarize(totals: dict) -> dict:
        invested = totals["total_invested"]
        payout = totals["total_payout"]
        bets = totals["total_bets"]
        hits = totals["hits"]
        return {
            "total_bets": bets,
            "total_invested": invested,
            "total_payout": payout,
            "profit": payout - invested,
            "roi": payout / invested if invested > 0 else 0.0,
            "hit_count": hits,
            "hit_rate": hits / bets if bets > 0 else 0.0,
        }

    return {
        "old": _summarize(old_totals),
        "new": _summarize(new_totals),
        "races_analyzed": len(rows),
    }
