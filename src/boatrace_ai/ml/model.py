"""LightGBM model management: loading, caching, and prediction."""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

from boatrace_ai import config
from boatrace_ai.data.models import PredictionResult, RaceProgram
from boatrace_ai.ml.bets import generate_bets
from boatrace_ai.ml.features import FEATURE_NAMES, extract_features

if TYPE_CHECKING:
    from boatrace_ai.data.odds import OddsData
    from boatrace_ai.ml.bets import BetRecommendation

log = logging.getLogger(__name__)

# Module-level cache
_cached_model = None
_cached_mtime: float = 0.0
_cached_calibrator = None
_cached_calibrator_mtime: float = 0.0


def _check_lightgbm() -> None:
    """Raise ImportError with a helpful message if lightgbm is not installed."""
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        raise ImportError(
            "ML機能には lightgbm が必要です。\n"
            "pip install 'boatrace-ai[ml]' でインストールしてください。"
        )


def load_model(model_path: Path | None = None):
    """Load LightGBM model with mtime-based caching.

    Returns a lightgbm.Booster instance.
    """
    import lightgbm as lgb

    global _cached_model, _cached_mtime

    path = model_path or config.MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"モデルファイルが見つかりません: {path}\n'boatrace train' でモデルを訓練してください。")

    current_mtime = path.stat().st_mtime
    if _cached_model is not None and _cached_mtime == current_mtime:
        return _cached_model

    log.info("Loading model from %s", path)
    _cached_model = lgb.Booster(model_file=str(path))
    _cached_mtime = current_mtime
    return _cached_model


def load_model_meta(meta_path: Path | None = None) -> dict:
    """Load model metadata (training date, metrics, etc.)."""
    path = meta_path or config.MODEL_META_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_calibrator(model_path: Path | None = None):
    """Load probability calibrator with mtime-based caching.

    Returns an IsotonicRegression instance or None if not available.
    """
    global _cached_calibrator, _cached_calibrator_mtime

    path = (model_path or config.MODEL_PATH).with_suffix(".calibrator.pkl")
    if not path.exists():
        return None

    current_mtime = path.stat().st_mtime
    if _cached_calibrator is not None and _cached_calibrator_mtime == current_mtime:
        return _cached_calibrator

    log.info("Loading calibrator from %s", path)
    _cached_calibrator = pickle.loads(path.read_bytes())
    _cached_calibrator_mtime = current_mtime
    return _cached_calibrator


def _predict_raw(
    race: RaceProgram, model_path: Path | None = None
) -> tuple[list[int], dict[int, float]]:
    """Internal: compute predicted_order and normalized probabilities.

    Uses softmax on raw LambdaRank scores, then applies isotonic
    calibration if a calibrator is available.

    Returns:
        (predicted_order, norm_probs) where norm_probs maps boat_number -> probability.
    """
    import numpy as np

    _check_lightgbm()

    model = load_model(model_path)
    calibrator = load_calibrator(model_path)

    # Extract features
    feature_rows = extract_features(race)
    feature_matrix = [[row[name] for name in FEATURE_NAMES] for row in feature_rows]

    # Get raw scores from LambdaRank model
    raw_scores = np.array(model.predict(feature_matrix))

    # Convert raw scores to probabilities via softmax
    exp_scores = np.exp(raw_scores - raw_scores.max())
    probs = exp_scores / exp_scores.sum()

    # Apply calibration if available
    if calibrator is not None:
        probs = calibrator.predict(probs)
        # Re-normalize after calibration
        total = probs.sum()
        if total > 0:
            probs = probs / total

    # Build boat_number -> probability mapping
    boat_probs: list[tuple[int, float]] = []
    for i, row in enumerate(feature_rows):
        boat_num = int(row["boat_number"])
        boat_probs.append((boat_num, float(probs[i])))

    # Sort by probability descending -> predicted order
    boat_probs.sort(key=lambda x: x[1], reverse=True)
    predicted_order = [bp[0] for bp in boat_probs]

    # Normalized probability map
    norm_probs = {bn: p for bn, p in boat_probs}

    return predicted_order, norm_probs


ODDS_BLEND_ALPHA = 0.7  # weight for model probability (0.3 for odds-implied)


def _blend_with_odds(
    norm_probs: dict[int, float],
    odds_win: dict[int, float],
    alpha: float = ODDS_BLEND_ALPHA,
) -> dict[int, float]:
    """Blend model probabilities with odds-implied probabilities.

    odds_implied_prob = 1/odds (normalized to sum to ~1 accounting for overround).
    final_prob = alpha * model_prob + (1-alpha) * odds_implied_prob
    """
    # Convert odds to implied probabilities
    implied: dict[int, float] = {}
    for boat_num, odds in odds_win.items():
        if odds > 0:
            implied[boat_num] = 1.0 / odds

    if not implied:
        return norm_probs

    # Normalize implied probabilities (remove overround)
    total_implied = sum(implied.values())
    if total_implied > 0:
        implied = {bn: p / total_implied for bn, p in implied.items()}

    # Blend
    blended: dict[int, float] = {}
    for bn in norm_probs:
        model_p = norm_probs[bn]
        odds_p = implied.get(bn, model_p)  # fallback to model if odds missing
        blended[bn] = alpha * model_p + (1 - alpha) * odds_p

    # Re-normalize
    total = sum(blended.values())
    if total > 0:
        blended = {bn: p / total for bn, p in blended.items()}

    return blended


def _build_prediction(
    race: RaceProgram,
    predicted_order: list[int],
    norm_probs: dict[int, float],
    odds_data: OddsData | None,
) -> PredictionResult:
    """Core prediction logic: confidence, bets, analysis → PredictionResult."""
    # Blend model probabilities with odds if available
    if odds_data is not None and odds_data.win:
        blended_probs = _blend_with_odds(norm_probs, odds_data.win)
        # Re-sort by blended probabilities
        sorted_boats = sorted(blended_probs.items(), key=lambda x: x[1], reverse=True)
        predicted_order = [bn for bn, _ in sorted_boats]
        norm_probs = blended_probs

    top_prob = norm_probs[predicted_order[0]]
    confidence = min(max(top_prob, 0.1), 0.95)

    if odds_data is not None:
        from boatrace_ai.ml.bets import generate_bets_ev

        ev_bets = generate_bets_ev(
            predicted_order,
            norm_probs,
            odds_win=odds_data.win,
            odds_exacta=odds_data.exacta,
            odds_quinella=odds_data.quinella,
            odds_trifecta=odds_data.trifecta,
            odds_trio=odds_data.trio,
        )
        recommended_bets = [b.to_bet_string() for b in ev_bets]
        _last_ev_bets_cache[:] = [ev_bets]
    else:
        ordered_probs = [norm_probs[bn] for bn in predicted_order]
        recommended_bets = generate_bets(predicted_order, ordered_probs)

    analysis = _build_analysis(race, predicted_order, norm_probs)

    return PredictionResult(
        predicted_order=predicted_order,
        confidence=round(confidence, 2),
        recommended_bets=recommended_bets,
        analysis=analysis,
    )


def predict_race_ml(
    race: RaceProgram,
    model_path: Path | None = None,
    odds_data: OddsData | None = None,
) -> PredictionResult:
    """Predict a single race using the ML model.

    Args:
        race: Race program data.
        model_path: Optional custom model path.
        odds_data: Optional OddsData from odds scraper. If provided,
                   uses EV-based bet generation with Kelly sizing.

    Returns PredictionResult with ML-derived order, confidence, bets, analysis.
    """
    predicted_order, norm_probs = _predict_raw(race, model_path)
    return _build_prediction(race, predicted_order, norm_probs, odds_data)


# Single-entry cache for the most recent EV bets (avoids memory leak)
_last_ev_bets_cache: list[list[BetRecommendation]] = []


def get_last_ev_bets(race: RaceProgram) -> list[BetRecommendation] | None:
    """Retrieve and consume the last EV bets generated (if any)."""
    if _last_ev_bets_cache:
        return _last_ev_bets_cache.pop()
    return None


def predict_race_ml_with_probs(
    race: RaceProgram,
    model_path: Path | None = None,
    odds_data: OddsData | None = None,
) -> tuple[PredictionResult, list[float]]:
    """Predict a race and return both PredictionResult and ordered probabilities.

    Returns:
        (PredictionResult, ordered_probs) where ordered_probs[i] is the
        probability of the i-th predicted boat finishing 1st.
    """
    predicted_order, norm_probs = _predict_raw(race, model_path)
    prediction = _build_prediction(race, predicted_order, norm_probs, odds_data)
    ordered_probs = [norm_probs[bn] for bn in predicted_order]
    return prediction, ordered_probs


def _build_analysis(
    race: RaceProgram,
    order: list[int],
    probs: dict[int, float],
) -> str:
    """Build a simple Japanese analysis string from ML predictions."""
    from boatrace_ai.data.constants import STADIUMS

    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    top3 = order[:3]
    top_probs = [f"{probs[bn]:.0%}" for bn in top3]

    lines = [
        f"【ML予測】{stadium} {race.race_number}R",
        f"本命: {top3[0]}号艇（勝率{top_probs[0]}）",
        f"対抗: {top3[1]}号艇（勝率{top_probs[1]}）",
        f"3着候補: {top3[2]}号艇（勝率{top_probs[2]}）",
    ]

    # Note if inner course is not favorite
    if top3[0] != 1:
        lines.append(f"※ インコース（1号艇）以外の{top3[0]}号艇を本命に据える波乱含みの予測。")

    return "\n".join(lines)
