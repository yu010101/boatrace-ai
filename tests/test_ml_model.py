"""Tests for ML model prediction with mocked LightGBM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from boatrace_ai.data.models import ProgramsResponse


def test_predict_race_ml_returns_prediction_result(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    # Mock lightgbm and numpy
    mock_model = MagicMock()
    # Return probabilities: boat 1 is highest
    mock_model.predict.return_value = [0.40, 0.15, 0.12, 0.08, 0.15, 0.10]

    with patch("boatrace_ai.ml.model.load_model", return_value=mock_model):
        with patch("boatrace_ai.ml.model._check_lightgbm"):
            import numpy  # noqa: F401

            with patch("boatrace_ai.ml.model.np", create=True):
                from boatrace_ai.ml.model import predict_race_ml

                result = predict_race_ml(race)

    assert result.predicted_order[0] == 1  # Boat 1 has highest prob
    assert len(result.predicted_order) == 6
    assert set(result.predicted_order) == {1, 2, 3, 4, 5, 6}
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.recommended_bets) >= 1
    assert len(result.analysis) > 0


def test_predict_race_ml_order_reflects_probabilities(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    mock_model = MagicMock()
    # Boat 3 (index 2) should be first, then boat 5 (index 4)
    mock_model.predict.return_value = [0.10, 0.15, 0.35, 0.08, 0.25, 0.07]

    with patch("boatrace_ai.ml.model.load_model", return_value=mock_model):
        with patch("boatrace_ai.ml.model._check_lightgbm"):
            from boatrace_ai.ml.model import predict_race_ml

            result = predict_race_ml(race)

    assert result.predicted_order[0] == 3  # Highest prob
    assert result.predicted_order[1] == 5  # Second highest


def test_predict_race_ml_no_model_raises(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    with patch("boatrace_ai.ml.model._check_lightgbm"):
        with patch("boatrace_ai.ml.model.config") as mock_config:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_config.MODEL_PATH = mock_path

            from boatrace_ai.ml.model import predict_race_ml

            with pytest.raises(FileNotFoundError, match="モデルファイルが見つかりません"):
                predict_race_ml(race)


def test_build_analysis_non_inner_favorite(programs_json: dict) -> None:
    """When top pick is not boat 1, analysis should note it."""
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    from boatrace_ai.ml.model import _build_analysis

    order = [3, 1, 5, 2, 4, 6]
    probs = {1: 0.20, 2: 0.10, 3: 0.35, 4: 0.08, 5: 0.17, 6: 0.10}

    analysis = _build_analysis(race, order, probs)

    assert "3号艇" in analysis
    assert "波乱" in analysis


def test_build_analysis_inner_favorite(programs_json: dict) -> None:
    """When top pick is boat 1, no 波乱 note."""
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    from boatrace_ai.ml.model import _build_analysis

    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 2: 0.12, 3: 0.20, 4: 0.08, 5: 0.12, 6: 0.08}

    analysis = _build_analysis(race, order, probs)

    assert "1号艇" in analysis
    assert "波乱" not in analysis
