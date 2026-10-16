"""Tests for prompt formatting."""

from __future__ import annotations

from boatrace_ai.data.models import ProgramsResponse
from boatrace_ai.prediction.prompts import PREDICTION_TOOL, format_race_for_prompt


def test_format_race_for_prompt(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]
    text = format_race_for_prompt(race)

    # Should contain stadium info and markdown table headers
    assert "桐生" in text or "場" in text
    assert "| 枠 |" in text
    assert "| 選手名 |" in text

    # Should contain all 6 boats
    for b in race.boats:
        assert b.racer_name in text
        assert str(b.racer_number) in text


def test_format_race_null_start_timing(programs_json: dict) -> None:
    """Null start timing should display as '-'."""
    programs_json["programs"][0]["boats"][0]["racer_average_start_timing"] = None
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]
    text = format_race_for_prompt(race)

    # The first boat row should have '-' for ST
    lines = text.split("\n")
    boat_1_line = [l for l in lines if f"| 1 |" in l][0]
    assert "| - |" in boat_1_line


def test_prediction_tool_schema() -> None:
    """PREDICTION_TOOL should have correct structure for Claude API."""
    assert PREDICTION_TOOL["name"] == "submit_prediction"
    schema = PREDICTION_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert "predicted_order" in schema["properties"]
    assert "confidence" in schema["properties"]
    assert "recommended_bets" in schema["properties"]
    assert "analysis" in schema["properties"]
    assert schema["properties"]["predicted_order"]["minItems"] == 6
    assert schema["properties"]["predicted_order"]["maxItems"] == 6
    assert set(schema["required"]) == {"predicted_order", "confidence", "recommended_bets", "analysis"}
