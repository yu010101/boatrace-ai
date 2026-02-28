"""Claude API prediction engine using tool_use for structured output."""

from __future__ import annotations

import logging

import anthropic

from boatrace_ai import config
from boatrace_ai.data.models import PredictionResult, RaceProgram
from boatrace_ai.prediction.prompts import (
    PREDICTION_TOOL,
    SYSTEM_PROMPT,
    format_race_for_prompt,
)

log = logging.getLogger(__name__)


class PredictionError(Exception):
    """Raised when a prediction fails."""


async def predict_race(race: RaceProgram) -> PredictionResult:
    """Call Claude API to predict a single race.

    Uses tool_use to force structured JSON output.
    Raises PredictionError on API or parsing failures.
    """
    config.validate()

    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    race_text = format_race_for_prompt(race)
    user_message = f"以下のレースの予測をお願いします。submit_predictionツールを使って予測結果を返してください。\n\n{race_text}"

    try:
        response = await client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[PREDICTION_TOOL],  # type: ignore[list-item]
            tool_choice={"type": "tool", "name": "submit_prediction"},
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.AuthenticationError:
        raise PredictionError("APIキーが無効です。ANTHROPIC_API_KEY を確認してください。")
    except anthropic.RateLimitError:
        raise PredictionError("APIレート制限に達しました。しばらく待ってから再実行してください。")
    except anthropic.APIConnectionError as e:
        raise PredictionError(f"API接続エラー: {e}")
    except anthropic.APIStatusError as e:
        raise PredictionError(f"APIエラー (HTTP {e.status_code}): {e.message}")

    # Extract tool_use block from response
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_prediction":
            try:
                return PredictionResult.model_validate(block.input)
            except Exception as e:
                log.error("Invalid prediction data from Claude: %s", block.input)
                raise PredictionError(f"予測データのパースに失敗: {e}") from e

    raise PredictionError("Claudeがsubmit_predictionツールを返しませんでした")


async def predict_races(races: list[RaceProgram]) -> list[tuple[RaceProgram, PredictionResult]]:
    """Predict multiple races sequentially.

    Sequential to respect rate limits and keep costs predictable.
    """
    results = []
    for race in races:
        prediction = await predict_race(race)
        results.append((race, prediction))
    return results
