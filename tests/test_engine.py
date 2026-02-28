"""Tests for the prediction engine with mocked Claude API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from boatrace_ai.data.models import ProgramsResponse
from boatrace_ai.prediction.engine import PredictionError, predict_race


def _make_mock_response() -> MagicMock:
    """Create a mock Claude API response with a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "submit_prediction"
    tool_block.input = {
        "predicted_order": [1, 3, 2, 5, 4, 6],
        "confidence": 0.65,
        "recommended_bets": ["3連単 1-3-2", "2連単 1-3"],
        "analysis": "1号艇がインから逃げ切り。3号艇がまくり差しで2着。",
    }

    response = MagicMock()
    response.content = [tool_block]
    return response


def _make_empty_response() -> MagicMock:
    """Response with no tool_use block."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "予測できません"

    response = MagicMock()
    response.content = [text_block]
    return response


@pytest.mark.asyncio
async def test_predict_race(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    mock_response = _make_mock_response()

    with patch("boatrace_ai.prediction.engine.config") as mock_config:
        mock_config.ANTHROPIC_API_KEY = "sk-ant-test"
        mock_config.MODEL = "claude-sonnet-4-20250514"
        mock_config.MAX_TOKENS = 2048
        mock_config.validate.return_value = None

        with patch("boatrace_ai.prediction.engine.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            prediction = await predict_race(race)

            assert prediction.predicted_order == [1, 3, 2, 5, 4, 6]
            assert prediction.confidence == 0.65
            assert len(prediction.recommended_bets) == 2
            assert "1号艇" in prediction.analysis

            # Verify API was called with correct params
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["tools"][0]["name"] == "submit_prediction"
            assert call_kwargs["tool_choice"]["name"] == "submit_prediction"


@pytest.mark.asyncio
async def test_predict_race_auth_error(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    with patch("boatrace_ai.prediction.engine.config") as mock_config:
        mock_config.ANTHROPIC_API_KEY = "sk-ant-invalid"
        mock_config.MODEL = "claude-sonnet-4-20250514"
        mock_config.MAX_TOKENS = 2048
        mock_config.validate.return_value = None

        with patch("boatrace_ai.prediction.engine.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=anthropic.AuthenticationError(
                    message="Invalid API key",
                    response=MagicMock(status_code=401),
                    body=None,
                )
            )
            mock_cls.return_value = mock_client

            with pytest.raises(PredictionError, match="APIキーが無効"):
                await predict_race(race)


@pytest.mark.asyncio
async def test_predict_race_rate_limit(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    with patch("boatrace_ai.prediction.engine.config") as mock_config:
        mock_config.ANTHROPIC_API_KEY = "sk-ant-test"
        mock_config.MODEL = "claude-sonnet-4-20250514"
        mock_config.MAX_TOKENS = 2048
        mock_config.validate.return_value = None

        with patch("boatrace_ai.prediction.engine.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=anthropic.RateLimitError(
                    message="Rate limited",
                    response=MagicMock(status_code=429),
                    body=None,
                )
            )
            mock_cls.return_value = mock_client

            with pytest.raises(PredictionError, match="レート制限"):
                await predict_race(race)


@pytest.mark.asyncio
async def test_predict_race_no_tool_use(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    with patch("boatrace_ai.prediction.engine.config") as mock_config:
        mock_config.ANTHROPIC_API_KEY = "sk-ant-test"
        mock_config.MODEL = "claude-sonnet-4-20250514"
        mock_config.MAX_TOKENS = 2048
        mock_config.validate.return_value = None

        with patch("boatrace_ai.prediction.engine.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=_make_empty_response())
            mock_cls.return_value = mock_client

            with pytest.raises(PredictionError, match="submit_prediction"):
                await predict_race(race)


@pytest.mark.asyncio
async def test_predict_race_missing_api_key(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    race = resp.programs[0]

    with patch("boatrace_ai.prediction.engine.config") as mock_config:
        mock_config.ANTHROPIC_API_KEY = ""
        mock_config.validate.side_effect = ValueError("ANTHROPIC_API_KEY が設定されていません")

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            await predict_race(race)
