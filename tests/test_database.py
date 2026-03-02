"""Tests for SQLite database operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from boatrace_ai.data.models import PredictionResult, RaceResult
from boatrace_ai.storage.database import (
    check_accuracy,
    get_accuracy_for_date,
    get_predictions_for_date,
    get_stats,
    init_db,
    save_prediction,
    save_result,
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    with patch("boatrace_ai.storage.database.config") as mock_config:
        mock_config.DB_PATH = db_path
        init_db()
        yield mock_config


def _make_prediction() -> PredictionResult:
    return PredictionResult(
        predicted_order=[1, 3, 2, 5, 4, 6],
        confidence=0.65,
        recommended_bets=["3連単 1-3-2"],
        analysis="テスト分析",
    )


def _make_result(actual_order: list[int] | None = None) -> RaceResult:
    if actual_order is None:
        actual_order = [3, 1, 2, 5, 4, 6]
    boats = []
    for i, boat_num in enumerate([1, 2, 3, 4, 5, 6]):
        place = actual_order.index(boat_num) + 1 if boat_num in actual_order else None
        boats.append({
            "racer_boat_number": boat_num,
            "racer_course_number": boat_num,
            "racer_start_timing": 0.15,
            "racer_place_number": place,
            "racer_number": 1000 + boat_num,
            "racer_name": f"選手{boat_num}",
        })
    return RaceResult.model_validate({
        "race_date": "2026-02-28",
        "race_stadium_number": 1,
        "race_number": 1,
        "race_wind": 3,
        "race_wind_direction_number": 5,
        "race_wave": 2,
        "race_weather_number": 1,
        "race_temperature": 15.0,
        "race_water_temperature": 12.0,
        "race_technique_number": 1,
        "boats": boats,
        "payouts": {
            "trifecta": [{"combination": "3-1-2", "payout": 1500}],
            "trio": [],
            "exacta": [],
            "quinella": [],
            "quinella_place": [],
            "win": [],
            "place": [],
        },
    })


def test_save_and_get_prediction() -> None:
    prediction = _make_prediction()
    save_prediction("2026-02-28", 1, 1, prediction)

    rows = get_predictions_for_date("2026-02-28")
    assert len(rows) == 1
    assert rows[0]["stadium_number"] == 1
    assert rows[0]["race_number"] == 1
    assert json.loads(rows[0]["predicted_order"]) == [1, 3, 2, 5, 4, 6]


def test_save_prediction_upsert() -> None:
    """Second save for same race should replace, not duplicate."""
    pred1 = _make_prediction()
    save_prediction("2026-02-28", 1, 1, pred1)

    pred2 = PredictionResult(
        predicted_order=[3, 1, 2, 5, 4, 6],
        confidence=0.8,
        recommended_bets=["3連単 3-1-2"],
        analysis="更新された分析",
    )
    save_prediction("2026-02-28", 1, 1, pred2)

    rows = get_predictions_for_date("2026-02-28")
    assert len(rows) == 1
    assert json.loads(rows[0]["predicted_order"]) == [3, 1, 2, 5, 4, 6]


def test_save_result() -> None:
    result = _make_result()
    save_result("2026-02-28", result)
    # No error = success (result stored)


def test_save_result_cancelled_race() -> None:
    """Cancelled race with no finishers should save NULL actual_order."""
    result = _make_result()
    # Clear all place numbers to simulate cancelled race
    for b in result.boats:
        b.racer_place_number = None
    save_result("2026-02-28", result)


def test_check_accuracy_hit() -> None:
    """Prediction matches result -> hit."""
    prediction = PredictionResult(
        predicted_order=[3, 1, 2, 5, 4, 6],
        confidence=0.7,
        recommended_bets=["3連単 3-1-2"],
        analysis="テスト",
    )
    save_prediction("2026-02-28", 1, 1, prediction)
    save_result("2026-02-28", _make_result([3, 1, 2, 5, 4, 6]))

    records = check_accuracy()
    assert len(records) == 1
    assert records[0]["hit_1st"] is True
    assert records[0]["hit_trifecta"] is True


def test_check_accuracy_miss() -> None:
    """Prediction doesn't match result -> miss."""
    save_prediction("2026-02-28", 1, 1, _make_prediction())
    save_result("2026-02-28", _make_result([3, 1, 2, 5, 4, 6]))

    records = check_accuracy()
    assert len(records) == 1
    assert records[0]["hit_1st"] is False
    assert records[0]["hit_trifecta"] is False


def test_check_accuracy_idempotent() -> None:
    """Second call should not return already-processed records."""
    save_prediction("2026-02-28", 1, 1, _make_prediction())
    save_result("2026-02-28", _make_result())

    records1 = check_accuracy()
    assert len(records1) == 1

    records2 = check_accuracy()
    assert len(records2) == 0


def test_get_stats_empty() -> None:
    stats = get_stats()
    assert stats["total_races"] == 0
    assert stats["hit_1st_rate"] == 0.0
    assert stats["hit_trifecta_rate"] == 0.0


def test_check_accuracy_corrupted_json(tmp_db) -> None:
    """Corrupted JSON in DB should be skipped, not crash."""
    save_prediction("2026-02-28", 1, 1, _make_prediction())
    save_result("2026-02-28", _make_result())

    # Corrupt the stored predicted_order JSON
    conn = sqlite3.connect(str(tmp_db.DB_PATH))
    conn.execute(
        "UPDATE predictions SET predicted_order = 'NOT VALID JSON' WHERE race_number = 1"
    )
    conn.commit()
    conn.close()

    # Should not crash, just skip the corrupted record
    records = check_accuracy()
    assert len(records) == 0


def test_get_stats_with_data() -> None:
    # Create 2 predictions + results
    pred_hit = PredictionResult(
        predicted_order=[3, 1, 2, 5, 4, 6],
        confidence=0.7,
        recommended_bets=[],
        analysis="hit",
    )
    save_prediction("2026-02-28", 1, 1, pred_hit)
    save_result("2026-02-28", _make_result([3, 1, 2, 5, 4, 6]))

    pred_miss = _make_prediction()  # predicts [1, 3, 2, ...]
    save_prediction("2026-02-28", 1, 2, pred_miss)
    # Create result for race 2
    result2 = _make_result([5, 4, 3, 2, 1, 6])
    result2.race_number = 2
    save_result("2026-02-28", result2)

    check_accuracy()
    stats = get_stats()

    assert stats["total_races"] == 2
    assert stats["hit_1st"] == 1
    assert stats["hit_1st_rate"] == 0.5


# ── get_accuracy_for_date ─────────────────────────────────


def test_get_accuracy_for_date_empty() -> None:
    """No accuracy records for date returns empty list."""
    records = get_accuracy_for_date("2026-03-01")
    assert records == []


def test_get_accuracy_for_date_returns_records() -> None:
    """After check_accuracy, records should be retrievable by date."""
    save_prediction("2026-02-28", 1, 1, _make_prediction())
    save_result("2026-02-28", _make_result())
    check_accuracy()

    records = get_accuracy_for_date("2026-02-28")
    assert len(records) == 1
    assert records[0]["stadium_number"] == 1
    assert records[0]["race_number"] == 1
    assert records[0]["hit_1st"] is False  # predicted 1, actual 3
    assert isinstance(records[0]["hit_1st"], bool)
    assert isinstance(records[0]["hit_trifecta"], bool)


def test_get_accuracy_for_date_ordered() -> None:
    """Records are ordered by stadium_number, race_number."""
    # Race at stadium 6, race 3
    pred1 = _make_prediction()
    save_prediction("2026-02-28", 6, 3, pred1)
    result1 = _make_result()
    result1.race_stadium_number = 6
    result1.race_number = 3
    save_result("2026-02-28", result1)

    # Race at stadium 1, race 1
    save_prediction("2026-02-28", 1, 1, _make_prediction())
    save_result("2026-02-28", _make_result())

    check_accuracy()

    records = get_accuracy_for_date("2026-02-28")
    assert len(records) == 2
    assert records[0]["stadium_number"] == 1
    assert records[1]["stadium_number"] == 6


def test_get_accuracy_for_date_filters_by_date() -> None:
    """Only records for the specified date are returned."""
    save_prediction("2026-02-28", 1, 1, _make_prediction())
    save_result("2026-02-28", _make_result())
    check_accuracy()

    records = get_accuracy_for_date("2026-03-01")
    assert records == []

    records = get_accuracy_for_date("2026-02-28")
    assert len(records) == 1
