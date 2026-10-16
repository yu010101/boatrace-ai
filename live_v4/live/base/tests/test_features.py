"""Tests for ML feature extraction."""

from __future__ import annotations

import pytest

from boatrace_ai.data.models import ProgramsResponse
from boatrace_ai.ml.features import CATEGORICAL_FEATURES, FEATURE_NAMES, extract_features


def test_extract_features_returns_6_rows(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    assert len(features) == 6


def test_extract_features_has_all_feature_names(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    for row in features:
        for name in FEATURE_NAMES:
            assert name in row, f"Missing feature: {name}"


def test_extract_features_correct_boat_numbers(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    boat_numbers = [int(row["boat_number"]) for row in features]
    assert sorted(boat_numbers) == [1, 2, 3, 4, 5, 6]


def test_extract_features_all_values_are_float(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    for row in features:
        for name, value in row.items():
            assert isinstance(value, float), f"{name} is {type(value)}, expected float"


def test_extract_features_ranks_are_valid(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    rank_features = ["national_top1_rank", "local_top1_rank", "motor_top2_rank", "avg_st_rank"]
    for rank_name in rank_features:
        ranks = sorted([row[rank_name] for row in features])
        assert ranks == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], f"Ranks for {rank_name} are not 1-6: {ranks}"


def test_extract_features_class_is_best_binary(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    for row in features:
        assert row["class_is_best_in_race"] in (0.0, 1.0)

    # At least one boat should be best
    assert any(row["class_is_best_in_race"] == 1.0 for row in features)


def test_extract_features_null_st_handling(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    # All boats in fixture have non-null ST
    features = extract_features(race)
    for row in features:
        assert row["is_null_st"] == 0.0


def test_extract_features_null_st_flag() -> None:
    """Test that null ST is handled with default value and flag."""
    from boatrace_ai.data.models import BoatEntry, RaceProgram

    boats = []
    for i in range(1, 7):
        b = BoatEntry(
            racer_boat_number=i,
            racer_name=f"選手{i}",
            racer_number=1000 + i,
            racer_class_number=3,
            racer_branch_number=1,
            racer_birthplace_number=1,
            racer_age=30,
            racer_weight=52.0,
            racer_flying_count=0,
            racer_late_count=0,
            racer_average_start_timing=0.15 if i != 3 else None,  # Boat 3 has null ST
            racer_national_top_1_percent=5.0,
            racer_national_top_2_percent=30.0,
            racer_national_top_3_percent=50.0,
            racer_local_top_1_percent=5.0,
            racer_local_top_2_percent=30.0,
            racer_local_top_3_percent=50.0,
            racer_assigned_motor_number=10 + i,
            racer_assigned_motor_top_2_percent=40.0,
            racer_assigned_motor_top_3_percent=55.0,
            racer_assigned_boat_number=20 + i,
            racer_assigned_boat_top_2_percent=35.0,
            racer_assigned_boat_top_3_percent=50.0,
        )
        boats.append(b)

    race = RaceProgram(
        race_date="2026-01-01",
        race_stadium_number=1,
        race_number=1,
        race_closed_at="2026-01-01 15:00:00",
        race_grade_number=5,
        race_title="テスト",
        race_subtitle="テスト",
        race_distance=1800,
        boats=boats,
    )

    features = extract_features(race)
    boat3 = [f for f in features if f["boat_number"] == 3.0][0]
    assert boat3["is_null_st"] == 1.0
    assert boat3["avg_start_timing"] == 0.20  # Default ST

    boat1 = [f for f in features if f["boat_number"] == 1.0][0]
    assert boat1["is_null_st"] == 0.0
    assert boat1["avg_start_timing"] == 0.15


def test_extract_features_stadium_and_grade(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    for row in features:
        assert row["stadium_number"] == float(race.race_stadium_number)
        assert row["grade_number"] == float(race.race_grade_number)


def test_feature_names_count() -> None:
    assert len(FEATURE_NAMES) == 35


def test_categorical_features_in_feature_names() -> None:
    for name in CATEGORICAL_FEATURES:
        assert name in FEATURE_NAMES


def test_pairwise_features(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    # Inner boat (boat 1) should have diff = 0 for inner_* features
    boat1 = [f for f in features if f["boat_number"] == 1.0][0]
    assert boat1["inner_national_top1_diff"] == 0.0
    assert boat1["inner_motor_top2_diff"] == 0.0
    assert boat1["is_inner_boat"] == 1.0

    # Other boats should have is_inner_boat = 0
    boat2 = [f for f in features if f["boat_number"] == 2.0][0]
    assert boat2["is_inner_boat"] == 0.0


def test_stadium_inner_win_rate(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    features = extract_features(race)

    # All boats in same race should have same stadium_inner_win_rate
    rates = [f["stadium_inner_win_rate"] for f in features]
    assert len(set(rates)) == 1
    assert 0.0 < rates[0] < 1.0
