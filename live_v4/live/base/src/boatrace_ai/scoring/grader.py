"""Race recommendation grading system.

Grades each race S/A/B/C based on ML prediction confidence.
S-rank races are the ones worth selling as premium predictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RaceGrade(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


@dataclass(frozen=True)
class GradeResult:
    grade: RaceGrade
    top1_prob: float
    top2_prob: float
    top3_prob: float
    reason: str


def grade_race(ordered_probs: list[float]) -> GradeResult:
    """Grade a race based on ordered prediction probabilities.

    Args:
        ordered_probs: Probabilities in predicted finish order
                       (index 0 = predicted 1st place prob, etc.)

    Returns:
        GradeResult with grade S/A/B/C and reasoning.
    """
    if len(ordered_probs) < 3:
        return GradeResult(
            grade=RaceGrade.C,
            top1_prob=ordered_probs[0] if ordered_probs else 0.0,
            top2_prob=0.0,
            top3_prob=0.0,
            reason="データ不足のため評価不可",
        )

    p1 = ordered_probs[0]
    top2 = p1 + ordered_probs[1]
    top3 = top2 + ordered_probs[2]

    if p1 >= 0.40 and top2 >= 0.55:
        grade = RaceGrade.S
        reason = f"本命確率{p1:.0%}、Top2合計{top2:.0%}の高確信レース"
    elif p1 >= 0.30 and top2 >= 0.45:
        grade = RaceGrade.A
        reason = f"本命確率{p1:.0%}、有力候補あり"
    elif p1 >= 0.20:
        grade = RaceGrade.B
        reason = f"本命確率{p1:.0%}、予測可能な範囲"
    else:
        grade = RaceGrade.C
        reason = f"本命確率{p1:.0%}、混戦模様のため見送り推奨"

    return GradeResult(
        grade=grade,
        top1_prob=round(p1, 4),
        top2_prob=round(top2, 4),
        top3_prob=round(top3, 4),
        reason=reason,
    )
