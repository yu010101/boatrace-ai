"""ROI tracking via virtual bets.

Matches recommended bets against actual race results to compute
simulated ROI — the most powerful sales metric for note.com articles.
"""

from __future__ import annotations

import json
import logging
from itertools import permutations

from boatrace_ai.storage.database import get_unchecked_bets, update_virtual_bet

log = logging.getLogger(__name__)

# Maps Japanese bet type names to payout JSON keys
BET_TYPE_MAP: dict[str, str] = {
    "3連単": "trifecta",
    "3連複": "trio",
    "2連単": "exacta",
    "2連複": "quinella",
    "単勝": "win",
}


def parse_bet_string(bet_str: str) -> tuple[str, str] | None:
    """Parse a bet string like '3連単 1-3-2' into (bet_type, combination).

    Returns None if the format is invalid.
    """
    parts = bet_str.split(" ", 1)
    if len(parts) != 2:
        return None
    bet_type, combination = parts
    if bet_type not in BET_TYPE_MAP:
        return None
    return bet_type, combination


def _normalize_combination(combination: str) -> list[str]:
    """Expand a combination into all matching patterns.

    - "1-3-2" (ordered) -> ["1-3-2"]
    - "1=2" (unordered pair) -> ["1-2", "2-1"]
    - "1=2=3" (unordered triple) -> all 6 permutations as "x-y-z"
    """
    if "=" in combination:
        nums = combination.split("=")
        return ["-".join(p) for p in permutations(nums)]
    return [combination]


def match_bet_to_payout(
    bet_type: str, combination: str, payouts_json: str, bet_amount: int = 1000,
) -> int:
    """Match a bet against payouts and return the payout amount.

    Args:
        bet_type: Japanese bet type ("3連単", "2連複", etc.)
        combination: Bet combination ("1-3-2", "1=2", etc.)
        payouts_json: JSON string of payouts from results table
        bet_amount: Actual bet amount in yen (default 1000)

    Returns:
        Payout amount scaled to actual bet amount (0 if no match).
    """
    payout_key = BET_TYPE_MAP.get(bet_type)
    if not payout_key:
        return 0

    try:
        payouts = json.loads(payouts_json)
    except (json.JSONDecodeError, TypeError):
        return 0

    payout_entries = payouts.get(payout_key, [])
    if not payout_entries:
        return 0

    # Expand combination into all matching patterns
    patterns = _normalize_combination(combination)

    for entry in payout_entries:
        entry_combo = entry.get("combination", "")
        if entry_combo in patterns:
            # Payouts are per 100 yen; scale to actual bet amount
            payout_per_100 = entry.get("payout", 0)
            return payout_per_100 * bet_amount // 100

    return 0


def calculate_roi(total_invested: int, total_payout: int) -> float:
    """Calculate ROI as a ratio. 1.0 = break even, 1.5 = 50% profit."""
    if total_invested <= 0:
        return 0.0
    return total_payout / total_invested


def check_virtual_bets() -> list[dict]:
    """Check all unchecked virtual bets against actual results.

    Returns list of checked bet dicts with is_hit and payout fields.
    """
    unchecked = get_unchecked_bets()
    checked: list[dict] = []

    for bet in unchecked:
        payout = match_bet_to_payout(
            bet["bet_type"],
            bet["combination"],
            bet["payouts_json"],
            bet_amount=bet.get("bet_amount", 1000),
        )
        is_hit = 1 if payout > 0 else 0
        update_virtual_bet(bet["id"], is_hit, payout)

        result = dict(bet)
        result["is_hit"] = is_hit
        result["payout"] = payout
        checked.append(result)

    return checked
