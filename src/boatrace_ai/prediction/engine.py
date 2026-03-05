"""Prediction engine: Claude API, ML, and hybrid modes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import anthropic

from boatrace_ai import config
from boatrace_ai.data.models import PredictionResult, RaceProgram

if TYPE_CHECKING:
    from boatrace_ai.data.odds import OddsData
from boatrace_ai.prediction.prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_TOOL,
    PREDICTION_TOOL,
    SYSTEM_PROMPT,
    format_ml_result_for_prompt,
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


async def predict_race_auto(
    race: RaceProgram, mode: str = "auto", odds_data: OddsData | None = None,
) -> PredictionResult:
    """Dispatcher: choose prediction method based on mode.

    Modes:
        auto    — Use ML if model exists, otherwise Claude.
        ml      — ML only (raises if no model).
        hybrid  — ML prediction + Claude analysis text.
        claude  — Claude only (original behavior).

    Args:
        odds_data: Optional OddsData for EV-based betting.
    """
    if mode == "auto":
        mode = "ml" if config.MODEL_PATH.exists() else "claude"

    if mode == "ml":
        from boatrace_ai.ml.model import predict_race_ml
        return predict_race_ml(race, odds_data=odds_data)
    elif mode == "hybrid":
        return await predict_race_hybrid(race, odds_data=odds_data)
    else:
        return await predict_race(race)


async def predict_race_hybrid(
    race: RaceProgram, odds_data: OddsData | None = None,
) -> PredictionResult:
    """Hybrid mode: ML prediction + Claude analysis.

    1. ML model produces order, confidence, bets.
    2. Claude generates analysis text explaining the ML prediction.
    3. Combined into a single PredictionResult.
    """
    from boatrace_ai.ml.model import predict_race_ml

    # Step 1: ML prediction (with odds if available)
    ml_result = predict_race_ml(race, odds_data=odds_data)

    # Step 2: Build probability map from ML analysis
    # Parse probabilities from the ML analysis (simple approach)
    from boatrace_ai.ml.features import FEATURE_NAMES, extract_features
    from boatrace_ai.ml.model import load_model

    model = load_model()
    feature_rows = extract_features(race)
    feature_matrix = [[row[name] for name in FEATURE_NAMES] for row in feature_rows]
    probs = model.predict(feature_matrix)

    # Build normalized prob map
    boat_probs: dict[int, float] = {}
    total_prob = sum(float(p) for p in probs)
    for i, row in enumerate(feature_rows):
        bn = int(row["boat_number"])
        boat_probs[bn] = float(probs[i]) / total_prob if total_prob > 0 else 1.0 / 6

    # Step 3: Claude analysis
    try:
        analysis = await _get_claude_analysis(race, ml_result.predicted_order, boat_probs)
    except Exception as e:
        log.warning("Claude analysis failed, using ML analysis: %s", e)
        analysis = ml_result.analysis

    return PredictionResult(
        predicted_order=ml_result.predicted_order,
        confidence=ml_result.confidence,
        recommended_bets=ml_result.recommended_bets,
        analysis=analysis,
    )


async def _get_claude_analysis(
    race: RaceProgram,
    predicted_order: list[int],
    probabilities: dict[int, float],
) -> str:
    """Call Claude API to generate analysis text for ML predictions."""
    config.validate()

    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    context = format_ml_result_for_prompt(race, predicted_order, probabilities)
    user_message = f"以下のAI予測結果について、レース展開予測を解説してください。submit_analysisツールで回答してください。\n\n{context}"

    try:
        response = await client.messages.create(
            model=config.MODEL,
            max_tokens=512,
            system=ANALYSIS_SYSTEM_PROMPT,
            tools=[ANALYSIS_TOOL],  # type: ignore[list-item]
            tool_choice={"type": "tool", "name": "submit_analysis"},
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        raise PredictionError(f"Claude解説生成に失敗: {e}") from e

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_analysis":
            return block.input.get("analysis", "")

    raise PredictionError("Claudeがsubmit_analysisツールを返しませんでした")
