"""Probability-based bet recommendation generation."""

from __future__ import annotations


def generate_bets(order: list[int], probs: list[float]) -> list[str]:
    """Generate recommended bets based on predicted order and probabilities.

    Args:
        order: Predicted finish order (boat numbers, 1st to 6th).
        probs: Corresponding normalized probabilities (same order as `order`).

    Returns:
        List of recommended bet strings.
    """
    if len(order) < 3 or len(probs) < 3:
        return []

    p1 = probs[0]  # P(predicted 1st finishes 1st)
    p2 = probs[1]  # P(predicted 2nd finishes 1st)
    p_top2 = p1 + p2
    p_top3 = p1 + p2 + probs[2]

    first, second, third = order[0], order[1], order[2]
    bets: list[str] = []

    if p1 >= 0.40:
        # Strong favorite -> single win
        bets.append(f"単勝 {first}")

    if p_top2 >= 0.55:
        # Top 2 confident -> exacta
        bets.append(f"2連単 {first}-{second}")
    elif p1 < 0.30:
        # Weak top pick -> quinella (order doesn't matter)
        bets.append(f"2連複 {first}={second}")

    if p_top3 >= 0.65:
        # Top 3 confident -> trifecta
        bets.append(f"3連単 {first}-{second}-{third}")
    elif p1 < 0.30:
        # Weak prediction -> trio (order doesn't matter)
        bets.append(f"3連複 {first}={second}={third}")

    # Always include at least one bet
    if not bets:
        bets.append(f"2連複 {first}={second}")

    return bets
