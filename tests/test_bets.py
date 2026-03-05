"""Tests for probability-based and EV-based bet generation."""

from __future__ import annotations

from boatrace_ai.ml.bets import (
    BetRecommendation,
    _kelly_bet,
    generate_bets,
    generate_bets_ev,
    harville_exacta,
    harville_quinella,
    harville_trifecta,
    harville_trio,
)


# ── Legacy generate_bets (backward compatibility) ────────


def test_strong_favorite_win_bet() -> None:
    """P(1st) >= 40% should recommend single win."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.45, 0.20, 0.15, 0.10, 0.06, 0.04]

    bets = generate_bets(order, probs)

    assert any("単勝" in b for b in bets)
    assert "単勝 1" in bets


def test_exacta_bet_when_top2_confident() -> None:
    """P(top2) >= 55% should recommend exacta."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.35, 0.25, 0.15, 0.12, 0.08, 0.05]

    bets = generate_bets(order, probs)

    assert any("2連単" in b for b in bets)
    assert "2連単 1-3" in bets


def test_trifecta_bet_when_top3_confident() -> None:
    """P(top3) >= 65% should recommend trifecta."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.40, 0.20, 0.15, 0.12, 0.08, 0.05]

    bets = generate_bets(order, probs)

    assert any("3連単" in b for b in bets)
    assert "3連単 1-3-2" in bets


def test_weak_favorite_conservative_bets() -> None:
    """P(1st) < 30% should recommend quinella/trio."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.25, 0.22, 0.18, 0.15, 0.12, 0.08]

    bets = generate_bets(order, probs)

    has_quinella = any("2連複" in b for b in bets)
    has_trio = any("3連複" in b for b in bets)
    assert has_quinella or has_trio


def test_always_returns_at_least_one_bet() -> None:
    """Even with moderate probabilities, at least one bet is returned."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.32, 0.20, 0.17, 0.14, 0.10, 0.07]

    bets = generate_bets(order, probs)

    assert len(bets) >= 1


def test_empty_input_returns_empty() -> None:
    """Empty or too-short input returns empty list."""
    assert generate_bets([], []) == []
    assert generate_bets([1], [0.5]) == []
    assert generate_bets([1, 2], [0.3, 0.7]) == []


def test_strong_favorite_all_bets() -> None:
    """Very strong favorite should get win + exacta + trifecta."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.50, 0.20, 0.12, 0.08, 0.06, 0.04]

    bets = generate_bets(order, probs)

    assert any("単勝" in b for b in bets)
    assert any("2連単" in b for b in bets)
    assert any("3連単" in b for b in bets)


# ── Harville approximation ───────────────────────────────


def test_harville_exacta() -> None:
    """P(1-2) = P(1) × P(2) / (1 - P(1))."""
    probs = {1: 0.40, 2: 0.25, 3: 0.15, 4: 0.10, 5: 0.06, 6: 0.04}
    p12 = harville_exacta(probs, 1, 2)
    expected = 0.40 * 0.25 / (1 - 0.40)
    assert abs(p12 - expected) < 1e-9


def test_harville_trifecta() -> None:
    """P(1-2-3) = P(1) × P(2)/(1-P(1)) × P(3)/(1-P(1)-P(2))."""
    probs = {1: 0.40, 2: 0.25, 3: 0.15, 4: 0.10, 5: 0.06, 6: 0.04}
    p123 = harville_trifecta(probs, 1, 2, 3)
    expected = 0.40 * (0.25 / 0.60) * (0.15 / 0.35)
    assert abs(p123 - expected) < 1e-9


def test_harville_quinella_symmetric() -> None:
    """P(1=2) = P(1-2) + P(2-1)."""
    probs = {1: 0.40, 2: 0.25, 3: 0.15, 4: 0.10, 5: 0.06, 6: 0.04}
    q12 = harville_quinella(probs, 1, 2)
    e12 = harville_exacta(probs, 1, 2)
    e21 = harville_exacta(probs, 2, 1)
    assert abs(q12 - (e12 + e21)) < 1e-9


def test_harville_trio_six_permutations() -> None:
    """P(1=2=3) should be sum of 6 trifecta permutations."""
    probs = {1: 0.40, 2: 0.25, 3: 0.15, 4: 0.10, 5: 0.06, 6: 0.04}
    trio = harville_trio(probs, 1, 2, 3)

    from itertools import permutations

    total = sum(harville_trifecta(probs, *p) for p in permutations([1, 2, 3]))
    assert abs(trio - total) < 1e-9


def test_harville_probabilities_sum_reasonable() -> None:
    """All 6 win probabilities should sum to ~1.0 (sanity check)."""
    probs = {1: 0.40, 2: 0.25, 3: 0.15, 4: 0.10, 5: 0.06, 6: 0.04}
    total = sum(probs.values())
    assert abs(total - 1.0) < 1e-9


# ── Kelly bet calculation ────────────────────────────────


def test_kelly_bet_positive_ev() -> None:
    """Positive EV should produce a non-zero bet."""
    amount = _kelly_bet(prob=0.40, odds=4.0, bankroll=100_000)
    assert amount >= 100
    assert amount <= 10_000


def test_kelly_bet_negative_ev() -> None:
    """Negative EV should produce zero bet."""
    amount = _kelly_bet(prob=0.10, odds=4.0, bankroll=100_000)
    # EV = 0.10 × 4.0 - 1 = -0.6 < 0
    assert amount == 0


def test_kelly_bet_minimum() -> None:
    """Very small edge should still meet minimum bet."""
    amount = _kelly_bet(prob=0.30, odds=4.0, bankroll=100_000)
    # EV = 0.30 × 4 - 1 = 0.2 > 0, but kelly fraction may be small
    assert amount >= 100


def test_kelly_bet_capped() -> None:
    """Very high edge should be capped at max bet."""
    amount = _kelly_bet(prob=0.90, odds=10.0, bankroll=1_000_000)
    assert amount <= 10_000


# ── EV-based bet generation ──────────────────────────────


def test_generate_bets_ev_with_strong_edge() -> None:
    """High-probability boat with good odds should generate win bet."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    odds_win = {1: 4.0, 2: 8.0, 3: 5.0, 4: 15.0, 5: 12.0, 6: 25.0}

    bets = generate_bets_ev(order, probs, odds_win=odds_win, min_ev=0.20)

    # Boat 1: EV = 0.40 × 4.0 - 1 = 0.6 > 0.20 ✓
    win_bets = [b for b in bets if b.bet_type == "単勝" and b.combination == "1"]
    assert len(win_bets) == 1
    assert abs(win_bets[0].ev - 0.6) < 1e-9


def test_generate_bets_ev_no_edge_no_bet() -> None:
    """Low odds for favorite should produce no bets (negative EV)."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    # Very low odds → no edge
    odds_win = {1: 1.5, 2: 2.0, 3: 1.8, 4: 3.0, 5: 2.5, 6: 4.0}

    bets = generate_bets_ev(order, probs, odds_win=odds_win, min_ev=0.20)

    # Boat 1: EV = 0.40 × 1.5 - 1 = -0.4 < 0.20, no bet
    win_bets = [b for b in bets if b.bet_type == "単勝"]
    assert len(win_bets) == 0


def test_generate_bets_ev_exacta() -> None:
    """Exacta bet should be generated when EV > threshold."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    odds_exacta = {"1-3": 20.0}  # High odds

    bets = generate_bets_ev(order, probs, odds_exacta=odds_exacta, min_ev=0.20)

    exacta_bets = [b for b in bets if b.bet_type == "2連単"]
    # P(1-3) = 0.40 × 0.25/0.60 ≈ 0.1667
    # EV = 0.1667 × 20 - 1 = 2.33 >> 0.20
    assert len(exacta_bets) >= 1
    assert exacta_bets[0].combination == "1-3"


def test_generate_bets_ev_trifecta() -> None:
    """Trifecta bet generated from Harville approximation."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    odds_trifecta = {"1-3-2": 200.0}  # Very high odds

    bets = generate_bets_ev(order, probs, odds_trifecta=odds_trifecta, min_ev=0.20)

    tri_bets = [b for b in bets if b.bet_type == "3連単"]
    assert len(tri_bets) >= 1


def test_generate_bets_ev_sorted_by_ev() -> None:
    """Bets should be sorted by EV descending."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    odds_win = {1: 4.0, 3: 8.0}  # Both have edge

    bets = generate_bets_ev(order, probs, odds_win=odds_win, min_ev=0.20)

    if len(bets) >= 2:
        for i in range(len(bets) - 1):
            assert bets[i].ev >= bets[i + 1].ev


def test_generate_bets_ev_empty_without_odds() -> None:
    """No odds → no bets."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}

    bets = generate_bets_ev(order, probs)
    assert bets == []


def test_generate_bets_ev_short_order() -> None:
    """Too-short order returns empty."""
    bets = generate_bets_ev([1, 2], {1: 0.5, 2: 0.5})
    assert bets == []


# ── BetRecommendation ────────────────────────────────────


def test_bet_recommendation_to_string() -> None:
    bet = BetRecommendation(
        bet_type="3連単",
        combination="1-3-2",
        model_prob=0.05,
        market_odds=200.0,
        ev=9.0,
        bet_amount=1000,
    )
    assert bet.to_bet_string() == "3連単 1-3-2"


def test_bet_recommendation_kelly_fraction() -> None:
    bet = BetRecommendation(
        bet_type="単勝",
        combination="1",
        model_prob=0.40,
        market_odds=4.0,
        ev=0.6,
        bet_amount=5000,
    )
    # f = 0.25 × (0.40 × 4.0 - 1) / (4.0 - 1) = 0.25 × 0.6 / 3 = 0.05
    assert abs(bet.kelly_fraction - 0.05) < 1e-9
