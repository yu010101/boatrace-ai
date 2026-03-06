"""Tests for training pipeline with mocked data."""

from __future__ import annotations

import pytest

from boatrace_ai.data.models import (
    BoatEntry,
    BoatResult,
    Payout,
    Payouts,
    ProgramsResponse,
    RaceProgram,
    RaceResult,
)
from boatrace_ai.ml.training import (
    _extract_labels,
    build_dataset,
    time_series_split,
)


def _make_race_program(race_date: str, stadium: int = 1, race_num: int = 1) -> RaceProgram:
    boats = []
    for i in range(1, 7):
        b = BoatEntry(
            racer_boat_number=i,
            racer_name=f"選手{i}",
            racer_number=1000 + i,
            racer_class_number=3,
            racer_branch_number=1,
            racer_birthplace_number=1,
            racer_age=30 + i,
            racer_weight=52.0 + i * 0.5,
            racer_flying_count=0,
            racer_late_count=0,
            racer_average_start_timing=0.15 + i * 0.01,
            racer_national_top_1_percent=5.0 + i,
            racer_national_top_2_percent=30.0 + i,
            racer_national_top_3_percent=50.0 + i,
            racer_local_top_1_percent=5.0 + i,
            racer_local_top_2_percent=30.0 + i,
            racer_local_top_3_percent=50.0 + i,
            racer_assigned_motor_number=10 + i,
            racer_assigned_motor_top_2_percent=40.0 + i,
            racer_assigned_motor_top_3_percent=55.0 + i,
            racer_assigned_boat_number=20 + i,
            racer_assigned_boat_top_2_percent=35.0 + i,
            racer_assigned_boat_top_3_percent=50.0 + i,
        )
        boats.append(b)

    return RaceProgram(
        race_date=race_date,
        race_stadium_number=stadium,
        race_number=race_num,
        race_closed_at=f"{race_date} 15:00:00",
        race_grade_number=5,
        race_title="テスト",
        race_subtitle="テスト",
        race_distance=1800,
        boats=boats,
    )


def _make_race_result(race_date: str, stadium: int = 1, race_num: int = 1, winner: int = 1) -> RaceResult:
    boats = []
    place = 1
    for i in range(1, 7):
        if i == winner:
            p = 1
        else:
            place += 1
            p = place - 1 if place <= 6 else place
        boats.append(
            BoatResult(
                racer_boat_number=i,
                racer_course_number=i,
                racer_start_timing=0.15,
                racer_place_number=1 if i == winner else (i if i < winner else i),
            )
        )

    # Fix place numbers to be unique 1-6
    used = {1}
    for b in boats:
        if b.racer_boat_number != winner:
            p = 2
            while p in used:
                p += 1
            b.racer_place_number = p
            used.add(p)

    empty_payouts = Payouts(
        trifecta=[Payout(combination="1-2-3", payout=1000)],
        trio=[Payout(combination="1=2=3", payout=500)],
        exacta=[Payout(combination="1-2", payout=300)],
        quinella=[Payout(combination="1=2", payout=200)],
        quinella_place=[Payout(combination="1=2", payout=100)],
        win=[Payout(combination="1", payout=150)],
        place=[Payout(combination="1", payout=100)],
    )

    return RaceResult(
        race_date=race_date,
        race_stadium_number=stadium,
        race_number=race_num,
        boats=boats,
        payouts=empty_payouts,
    )


def test_extract_labels_winner_boat1() -> None:
    result = _make_race_result("2026-01-01", winner=1)
    labels = _extract_labels(result)

    assert len(labels) == 6
    assert labels[0] == 6  # Boat 1 is winner (relevance 6)
    assert max(labels) == 6  # Winner has highest relevance


def test_extract_labels_winner_boat3() -> None:
    result = _make_race_result("2026-01-01", winner=3)
    labels = _extract_labels(result)

    assert labels[2] == 6  # Boat 3 (index 2) is winner (relevance 6)
    assert labels[0] != 6  # Boat 1 is not the winner


def test_build_dataset_produces_correct_shape() -> None:
    pairs = [
        (_make_race_program("2026-01-01"), _make_race_result("2026-01-01", winner=1)),
        (_make_race_program("2026-01-02"), _make_race_result("2026-01-02", winner=3)),
    ]

    X, y, groups = build_dataset(pairs)

    assert len(X) == 12  # 2 races x 6 boats
    assert len(y) == 12
    assert all(len(row) == 29 for row in X)  # 29 features
    assert groups == [6, 6]  # 2 races with 6 boats each


def test_build_dataset_labels_are_relevance_scores() -> None:
    pairs = [
        (_make_race_program("2026-01-01"), _make_race_result("2026-01-01", winner=2)),
    ]

    X, y, groups = build_dataset(pairs)

    assert all(0 <= label <= 6 for label in y)
    assert max(y) == 6  # Winner has relevance 6


def test_time_series_split_basic() -> None:
    dates = [f"2026-01-{d:02d}" for d in range(1, 16)]
    pairs = [
        (_make_race_program(d), _make_race_result(d, winner=1))
        for d in dates
    ]

    train, val = time_series_split(pairs, val_days=5)

    assert len(train) > 0
    assert len(val) > 0
    assert len(train) + len(val) == len(pairs)

    # All train dates should be before all val dates
    train_dates = {p.race_date for p, _ in train}
    val_dates = {p.race_date for p, _ in val}
    assert max(train_dates) < min(val_dates)


def test_time_series_split_empty() -> None:
    train, val = time_series_split([], val_days=5)
    assert train == []
    assert val == []


def test_time_series_split_insufficient_days() -> None:
    """When fewer days than val_days, all data goes to training."""
    pairs = [
        (_make_race_program("2026-01-01"), _make_race_result("2026-01-01", winner=1)),
        (_make_race_program("2026-01-02"), _make_race_result("2026-01-02", winner=2)),
    ]

    train, val = time_series_split(pairs, val_days=5)

    assert len(train) == 2
    assert len(val) == 0
