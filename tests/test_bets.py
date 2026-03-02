"""Tests for probability-based bet generation."""

from __future__ import annotations

from boatrace_ai.ml.bets import generate_bets


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
