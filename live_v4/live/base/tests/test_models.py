"""Tests for Pydantic models."""

import pytest

from boatrace_ai.data.models import (
    PredictionResult,
    ProgramsResponse,
    ResultsResponse,
)


def test_programs_parse(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    assert len(resp.programs) > 0
    race = resp.programs[0]
    assert race.race_stadium_number >= 1
    assert race.race_number >= 1
    assert len(race.boats) == 6
    boat = race.boats[0]
    assert boat.racer_boat_number == 1
    assert boat.racer_name


def test_programs_nullable_start_timing(programs_json: dict) -> None:
    """racer_average_start_timing can be None in real API data."""
    programs_json["programs"][0]["boats"][0]["racer_average_start_timing"] = None
    resp = ProgramsResponse.model_validate(programs_json)
    assert resp.programs[0].boats[0].racer_average_start_timing is None


def test_results_parse(results_json: dict) -> None:
    resp = ResultsResponse.model_validate(results_json)
    assert len(resp.results) > 0
    result = resp.results[0]
    assert result.race_stadium_number >= 1
    assert len(result.boats) == 6


def test_prediction_model_valid() -> None:
    p = PredictionResult(
        predicted_order=[1, 3, 2, 5, 4, 6],
        confidence=0.72,
        recommended_bets=["3連単 1-3-2", "2連単 1-3"],
        analysis="1号艇のA1級選手がインから逃げ切り濃厚。",
    )
    assert p.predicted_order[0] == 1
    assert p.confidence == 0.72
    assert len(p.recommended_bets) == 2


def test_prediction_model_invalid_order_length() -> None:
    with pytest.raises(ValueError, match="6 elements"):
        PredictionResult(
            predicted_order=[1, 2, 3],
            confidence=0.5,
            recommended_bets=[],
            analysis="test",
        )


def test_prediction_model_invalid_order_values() -> None:
    with pytest.raises(ValueError, match="boats 1-6"):
        PredictionResult(
            predicted_order=[1, 2, 3, 4, 5, 7],
            confidence=0.5,
            recommended_bets=[],
            analysis="test",
        )


def test_prediction_model_duplicate_boats() -> None:
    with pytest.raises(ValueError, match="boats 1-6"):
        PredictionResult(
            predicted_order=[1, 1, 2, 3, 4, 5],
            confidence=0.5,
            recommended_bets=[],
            analysis="test",
        )


def test_prediction_model_invalid_confidence_high() -> None:
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        PredictionResult(
            predicted_order=[1, 2, 3, 4, 5, 6],
            confidence=1.5,
            recommended_bets=[],
            analysis="test",
        )


def test_prediction_model_invalid_confidence_negative() -> None:
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        PredictionResult(
            predicted_order=[1, 2, 3, 4, 5, 6],
            confidence=-0.1,
            recommended_bets=[],
            analysis="test",
        )
