"""Tests for scoring/grader.py — race recommendation grading."""

from __future__ import annotations

from boatrace_ai.scoring.grader import GradeResult, RaceGrade, grade_race


def test_grade_s_rank() -> None:
    """High confidence → S rank."""
    # p1=0.45, p2=0.20 → top2=0.65 ≥ 0.55
    probs = [0.45, 0.20, 0.15, 0.10, 0.06, 0.04]
    result = grade_race(probs)
    assert result.grade == RaceGrade.S
    assert result.top1_prob == 0.45
    assert "高確信" in result.reason


def test_grade_s_requires_both_conditions() -> None:
    """p1 ≥ 0.40 but top2 < 0.55 → not S."""
    probs = [0.42, 0.10, 0.15, 0.13, 0.12, 0.08]
    result = grade_race(probs)
    # top2 = 0.42 + 0.10 = 0.52 < 0.55
    assert result.grade != RaceGrade.S


def test_grade_a_rank() -> None:
    """Moderate confidence → A rank."""
    # p1=0.35, p2=0.15 → top2=0.50 ≥ 0.45
    probs = [0.35, 0.15, 0.15, 0.15, 0.10, 0.10]
    result = grade_race(probs)
    assert result.grade == RaceGrade.A
    assert "有力候補" in result.reason


def test_grade_b_rank() -> None:
    """Lower confidence → B rank."""
    # p1=0.25, top2=0.40 < 0.45
    probs = [0.25, 0.15, 0.15, 0.15, 0.15, 0.15]
    result = grade_race(probs)
    assert result.grade == RaceGrade.B
    assert "予測可能" in result.reason


def test_grade_c_rank() -> None:
    """Low confidence → C rank."""
    # p1=0.18 < 0.20
    probs = [0.18, 0.17, 0.17, 0.16, 0.16, 0.16]
    result = grade_race(probs)
    assert result.grade == RaceGrade.C
    assert "混戦" in result.reason


def test_grade_race_returns_grade_result() -> None:
    """Return type is GradeResult with all fields."""
    probs = [0.45, 0.20, 0.15, 0.10, 0.06, 0.04]
    result = grade_race(probs)
    assert isinstance(result, GradeResult)
    assert isinstance(result.grade, RaceGrade)
    assert isinstance(result.top1_prob, float)
    assert isinstance(result.top2_prob, float)
    assert isinstance(result.top3_prob, float)
    assert isinstance(result.reason, str)


def test_grade_probs_are_rounded() -> None:
    """Probabilities should be rounded to 4 decimal places."""
    probs = [0.333333, 0.222222, 0.111111, 0.111111, 0.111111, 0.111111]
    result = grade_race(probs)
    assert result.top1_prob == round(0.333333, 4)


def test_grade_short_probs_list() -> None:
    """List with < 3 items should return C grade."""
    result = grade_race([0.5, 0.5])
    assert result.grade == RaceGrade.C
    assert "データ不足" in result.reason


def test_grade_empty_probs() -> None:
    """Empty list should return C grade."""
    result = grade_race([])
    assert result.grade == RaceGrade.C


def test_grade_boundary_s_exact() -> None:
    """Exactly at S boundary."""
    # p1=0.40, top2=0.55 → S rank
    probs = [0.40, 0.15, 0.15, 0.12, 0.10, 0.08]
    result = grade_race(probs)
    assert result.grade == RaceGrade.S


def test_grade_boundary_a_exact() -> None:
    """Exactly at A boundary."""
    # p1=0.30, p2=0.20 → top2=0.50 ≥ 0.45 → A rank
    probs = [0.30, 0.20, 0.15, 0.15, 0.10, 0.10]
    result = grade_race(probs)
    assert result.grade == RaceGrade.A


def test_grade_boundary_b_exact() -> None:
    """Exactly at B boundary."""
    # p1=0.20, top2=0.35 < 0.45 → B rank
    probs = [0.20, 0.15, 0.15, 0.17, 0.17, 0.16]
    result = grade_race(probs)
    assert result.grade == RaceGrade.B


def test_race_grade_enum_values() -> None:
    """RaceGrade enum values are correct strings."""
    assert RaceGrade.S.value == "S"
    assert RaceGrade.A.value == "A"
    assert RaceGrade.B.value == "B"
    assert RaceGrade.C.value == "C"


def test_grade_result_frozen() -> None:
    """GradeResult should be immutable (frozen dataclass)."""
    result = grade_race([0.45, 0.20, 0.15, 0.10, 0.06, 0.04])
    import pytest
    with pytest.raises(AttributeError):
        result.grade = RaceGrade.C  # type: ignore[misc]
