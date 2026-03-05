"""EV-based bet recommendation with Kelly criterion sizing.

Replaces the old probability-threshold approach with expected value (EV)
calculations using market odds. Only bets with EV > threshold are generated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from boatrace_ai import config

log = logging.getLogger(__name__)

# ── Configuration (sourced from config.py / env vars) ────

MIN_EV: float = config.EV_MIN
KELLY_FRACTION: float = config.EV_KELLY_FRACTION
MIN_BET = 100  # ¥100 minimum
MAX_BET = 10_000  # ¥10,000 cap
DEFAULT_BANKROLL: int = config.EV_BANKROLL


@dataclass
class BetRecommendation:
    """A single bet recommendation with EV and Kelly sizing."""

    bet_type: str  # "単勝", "2連単", "2連複", "3連単", "3連複"
    combination: str  # "1", "1-3", "1=3", "1-3-2", "1=2=3"
    model_prob: float  # Model-estimated probability
    market_odds: float  # Decimal odds from boatrace.jp
    ev: float  # Expected value: prob × odds - 1
    bet_amount: int  # Kelly-sized bet in yen

    def to_bet_string(self) -> str:
        """Format as legacy bet string for backward compatibility.

        e.g. "3連単 1-3-2"
        """
        return f"{self.bet_type} {self.combination}"

    @property
    def kelly_fraction(self) -> float:
        """Raw Kelly fraction before bankroll scaling."""
        if self.market_odds <= 1.0:
            return 0.0
        return KELLY_FRACTION * (self.model_prob * self.market_odds - 1) / (self.market_odds - 1)


# ── Harville approximation ───────────────────────────────


def harville_exacta(probs: dict[int, float], a: int, b: int) -> float:
    """P(A finishes 1st AND B finishes 2nd) using Harville model.

    P(A-B) = P(A) × P(B) / (1 - P(A))
    """
    pa = probs.get(a, 0.0)
    pb = probs.get(b, 0.0)
    denom = 1.0 - pa
    if denom <= 0:
        return 0.0
    return pa * pb / denom


def harville_trifecta(probs: dict[int, float], a: int, b: int, c: int) -> float:
    """P(A-B-C finish 1st-2nd-3rd) using Harville model.

    P(A-B-C) = P(A) × P(B)/(1-P(A)) × P(C)/(1-P(A)-P(B))
    """
    pa = probs.get(a, 0.0)
    pb = probs.get(b, 0.0)
    pc = probs.get(c, 0.0)
    d1 = 1.0 - pa
    d2 = 1.0 - pa - pb
    if d1 <= 0 or d2 <= 0:
        return 0.0
    return pa * (pb / d1) * (pc / d2)


def harville_quinella(probs: dict[int, float], a: int, b: int) -> float:
    """P(A and B finish in top 2, any order).

    P(A=B) = P(A-B) + P(B-A)
    """
    return harville_exacta(probs, a, b) + harville_exacta(probs, b, a)


def harville_trio(probs: dict[int, float], a: int, b: int, c: int) -> float:
    """P(A, B, C finish in top 3, any order).

    Sum of all 6 permutations of (A, B, C).
    """
    from itertools import permutations

    return sum(harville_trifecta(probs, *perm) for perm in permutations([a, b, c]))


# ── EV + Kelly calculation ───────────────────────────────


def _kelly_bet(
    prob: float, odds: float, bankroll: int = DEFAULT_BANKROLL,
    kelly_fraction: float = KELLY_FRACTION,
) -> int:
    """Compute Kelly-fraction bet amount in yen.

    f = fraction × (p × odds - 1) / (odds - 1)
    """
    if odds <= 1.0 or prob <= 0:
        return 0
    edge = prob * odds - 1
    if edge <= 0:
        return 0
    f = kelly_fraction * edge / (odds - 1)
    amount = int(bankroll * f)
    # Round to nearest 100
    amount = (amount // 100) * 100
    return max(MIN_BET, min(amount, MAX_BET))


def generate_bets_ev(
    order: list[int],
    probs: dict[int, float],
    odds_win: dict[int, float] | None = None,
    odds_exacta: dict[str, float] | None = None,
    odds_quinella: dict[str, float] | None = None,
    odds_trifecta: dict[str, float] | None = None,
    odds_trio: dict[str, float] | None = None,
    bankroll: int = DEFAULT_BANKROLL,
    min_ev: float = MIN_EV,
    kelly_fraction: float = KELLY_FRACTION,
) -> list[BetRecommendation]:
    """Generate EV-positive bet recommendations.

    Only bets where EV > min_ev are included.
    Bet amounts are sized by Kelly criterion.

    Args:
        order: Predicted finish order [1st, 2nd, 3rd, ...] (boat numbers).
        probs: Normalized probabilities {boat_number: P(win)}.
        odds_*: Market odds from boatrace.jp (None = skip that bet type).
        bankroll: Assumed bankroll for Kelly sizing.
        min_ev: Minimum EV threshold (default 0.20 = 20% edge).

    Returns:
        List of BetRecommendation sorted by EV descending.
    """
    if len(order) < 3:
        return []

    bets: list[BetRecommendation] = []
    first, second, third = order[0], order[1], order[2]

    # ── Win (単勝) ──
    if odds_win:
        for boat in order[:3]:  # Check top 3 candidates
            market_odds = odds_win.get(boat)
            if market_odds is None:
                continue
            p = probs.get(boat, 0.0)
            ev = p * market_odds - 1
            if ev > min_ev:
                bets.append(BetRecommendation(
                    bet_type="単勝",
                    combination=str(boat),
                    model_prob=p,
                    market_odds=market_odds,
                    ev=ev,
                    bet_amount=_kelly_bet(p, market_odds, bankroll, kelly_fraction),
                ))

    # ── Exacta (2連単) ──
    if odds_exacta:
        # Check top predicted exacta combinations
        for a, b in [(first, second), (first, third), (second, first), (second, third)]:
            key = f"{a}-{b}"
            market_odds = odds_exacta.get(key)
            if market_odds is None:
                continue
            p = harville_exacta(probs, a, b)
            ev = p * market_odds - 1
            if ev > min_ev:
                bets.append(BetRecommendation(
                    bet_type="2連単",
                    combination=key,
                    model_prob=p,
                    market_odds=market_odds,
                    ev=ev,
                    bet_amount=_kelly_bet(p, market_odds, bankroll, kelly_fraction),
                ))

    # ── Quinella (2連複) ──
    if odds_quinella:
        for a, b in [(first, second), (first, third), (second, third)]:
            key = f"{min(a, b)}-{max(a, b)}"
            market_odds = odds_quinella.get(key)
            if market_odds is None:
                continue
            p = harville_quinella(probs, a, b)
            ev = p * market_odds - 1
            if ev > min_ev:
                bets.append(BetRecommendation(
                    bet_type="2連複",
                    combination=f"{min(a, b)}={max(a, b)}",
                    model_prob=p,
                    market_odds=market_odds,
                    ev=ev,
                    bet_amount=_kelly_bet(p, market_odds, bankroll, kelly_fraction),
                ))

    # ── Trifecta (3連単) ──
    if odds_trifecta:
        # Check top trifecta permutations
        from itertools import permutations as perms

        top3 = order[:3]
        for perm in perms(top3):
            key = f"{perm[0]}-{perm[1]}-{perm[2]}"
            market_odds = odds_trifecta.get(key)
            if market_odds is None:
                continue
            p = harville_trifecta(probs, *perm)
            ev = p * market_odds - 1
            if ev > min_ev:
                bets.append(BetRecommendation(
                    bet_type="3連単",
                    combination=key,
                    model_prob=p,
                    market_odds=market_odds,
                    ev=ev,
                    bet_amount=_kelly_bet(p, market_odds, bankroll, kelly_fraction),
                ))

    # ── Trio (3連複) ──
    if odds_trio:
        boats = sorted([first, second, third])
        key = f"{boats[0]}-{boats[1]}-{boats[2]}"
        market_odds = odds_trio.get(key)
        if market_odds is not None:
            p = harville_trio(probs, *boats)
            ev = p * market_odds - 1
            if ev > min_ev:
                bets.append(BetRecommendation(
                    bet_type="3連複",
                    combination=f"{boats[0]}={boats[1]}={boats[2]}",
                    model_prob=p,
                    market_odds=market_odds,
                    ev=ev,
                    bet_amount=_kelly_bet(p, market_odds, bankroll, kelly_fraction),
                ))

    # Sort by EV descending
    bets.sort(key=lambda b: b.ev, reverse=True)
    return bets


# ── Legacy compatibility ─────────────────────────────────


def generate_bets(order: list[int], probs: list[float]) -> list[str]:
    """Legacy interface: generate bets without odds (probability-threshold only).

    Kept for backward compatibility when odds are not available.
    """
    if len(order) < 3 or len(probs) < 3:
        return []

    p1 = probs[0]
    p2 = probs[1]
    p_top2 = p1 + p2
    p_top3 = p1 + p2 + probs[2]

    first, second, third = order[0], order[1], order[2]
    bets: list[str] = []

    if p1 >= 0.40:
        bets.append(f"単勝 {first}")

    if p_top2 >= 0.55:
        bets.append(f"2連単 {first}-{second}")
    elif p1 < 0.30:
        bets.append(f"2連複 {first}={second}")

    if p_top3 >= 0.65:
        bets.append(f"3連単 {first}-{second}-{third}")
    elif p1 < 0.30:
        bets.append(f"3連複 {first}={second}={third}")

    if not bets:
        bets.append(f"2連複 {first}={second}")

    return bets
