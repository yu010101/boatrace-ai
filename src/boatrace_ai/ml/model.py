"""LightGBM model management: loading, caching, and prediction."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from boatrace_ai import config
from boatrace_ai.data.models import PredictionResult, RaceProgram
from boatrace_ai.ml.bets import generate_bets
from boatrace_ai.ml.features import FEATURE_NAMES, extract_features

log = logging.getLogger(__name__)

# Module-level cache
_cached_model = None
_cached_mtime: float = 0.0


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


def _predict_raw(
    race: RaceProgram, model_path: Path | None = None
) -> tuple[list[int], dict[int, float]]:
    """Internal: compute predicted_order and normalized probabilities.

    Returns:
        (predicted_order, norm_probs) where norm_probs maps boat_number -> probability.
    """
    _check_lightgbm()

    model = load_model(model_path)

    # Extract features
    feature_rows = extract_features(race)
    feature_matrix = [[row[name] for name in FEATURE_NAMES] for row in feature_rows]

    # Predict P(1st place) for each boat
    probs = model.predict(feature_matrix)

    # Build boat_number -> probability mapping
    boat_probs: list[tuple[int, float]] = []
    for i, row in enumerate(feature_rows):
        boat_num = int(row["boat_number"])
        boat_probs.append((boat_num, float(probs[i])))

    # Sort by probability descending -> predicted order
    boat_probs.sort(key=lambda x: x[1], reverse=True)
    predicted_order = [bp[0] for bp in boat_probs]

    # Normalize probabilities to sum to 1
    total_prob = sum(p for _, p in boat_probs)
    if total_prob > 0:
        norm_probs = {bn: p / total_prob for bn, p in boat_probs}
    else:
        norm_probs = {bn: 1.0 / 6 for bn, _ in boat_probs}

    return predicted_order, norm_probs


def predict_race_ml(race: RaceProgram, model_path: Path | None = None) -> PredictionResult:
    """Predict a single race using the ML model.

    Returns PredictionResult with ML-derived order, confidence, bets, analysis.
    """
    predicted_order, norm_probs = _predict_raw(race, model_path)

    # Confidence: based on how dominant the top prediction is
    top_prob = norm_probs[predicted_order[0]]
    confidence = min(max(top_prob * 1.5, 0.1), 0.95)  # Scale up, clamp to [0.1, 0.95]

    # Generate recommended bets
    ordered_probs = [norm_probs[bn] for bn in predicted_order]
    recommended_bets = generate_bets(predicted_order, ordered_probs)

    # Generate simple analysis
    analysis = _build_analysis(race, predicted_order, norm_probs)

    return PredictionResult(
        predicted_order=predicted_order,
        confidence=round(confidence, 2),
        recommended_bets=recommended_bets,
        analysis=analysis,
    )


def predict_race_ml_with_probs(
    race: RaceProgram, model_path: Path | None = None
) -> tuple[PredictionResult, list[float]]:
    """Predict a race and return both PredictionResult and ordered probabilities.

    Returns:
        (PredictionResult, ordered_probs) where ordered_probs[i] is the
        probability of the i-th predicted boat finishing 1st.
    """
    predicted_order, norm_probs = _predict_raw(race, model_path)

    top_prob = norm_probs[predicted_order[0]]
    confidence = min(max(top_prob * 1.5, 0.1), 0.95)

    ordered_probs = [norm_probs[bn] for bn in predicted_order]
    recommended_bets = generate_bets(predicted_order, ordered_probs)
    analysis = _build_analysis(race, predicted_order, norm_probs)

    prediction = PredictionResult(
        predicted_order=predicted_order,
        confidence=round(confidence, 2),
        recommended_bets=recommended_bets,
        analysis=analysis,
    )

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
