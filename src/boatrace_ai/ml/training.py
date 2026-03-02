"""Training pipeline: data collection, feature extraction, model training."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from boatrace_ai import config
from boatrace_ai.data.client import fetch_programs, fetch_results
from boatrace_ai.data.models import ProgramsResponse, RaceProgram, RaceResult, ResultsResponse
from boatrace_ai.ml.features import FEATURE_NAMES, extract_features

log = logging.getLogger(__name__)

LGBM_PARAMS: dict = {
    "objective": "binary",
    "metric": "binary_logloss",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
    "verbose": -1,
}

N_ESTIMATORS = 500
EARLY_STOPPING_ROUNDS = 50
SEMAPHORE_LIMIT = 5


async def _fetch_day(
    d: date,
    semaphore: asyncio.Semaphore,
) -> tuple[ProgramsResponse | None, ResultsResponse | None]:
    """Fetch programs and results for a single date, with concurrency control."""
    async with semaphore:
        programs = None
        results = None
        try:
            programs = await fetch_programs(d)
        except Exception as e:
            log.debug("Programs fetch failed for %s: %s", d, e)
        try:
            results = await fetch_results(d)
        except Exception as e:
            log.debug("Results fetch failed for %s: %s", d, e)
        return programs, results


async def collect_training_data(
    days: int = 90,
    progress_callback=None,
) -> list[tuple[RaceProgram, RaceResult]]:
    """Collect program+result pairs for past N days.

    Returns list of (program, result) tuples for races that have both data.
    """
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(1, days + 1)]

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)

    tasks = [_fetch_day(d, semaphore) for d in dates]
    day_results = await asyncio.gather(*tasks)

    # Build result lookup: (date, stadium, race_number) -> RaceResult
    result_lookup: dict[tuple[str, int, int], RaceResult] = {}
    for _, results_resp in day_results:
        if results_resp is None:
            continue
        for result in results_resp.results:
            has_results = any(b.racer_place_number is not None for b in result.boats)
            if has_results:
                key = (result.race_date, result.race_stadium_number, result.race_number)
                result_lookup[key] = result

    # Match programs with results
    paired: list[tuple[RaceProgram, RaceResult]] = []
    for programs_resp, _ in day_results:
        if programs_resp is None:
            continue
        for program in programs_resp.programs:
            if len(program.boats) != 6:
                continue
            key = (program.race_date, program.race_stadium_number, program.race_number)
            if key in result_lookup:
                paired.append((program, result_lookup[key]))

    if progress_callback:
        progress_callback(len(paired), len(dates))

    log.info("Collected %d race pairs from %d days", len(paired), days)
    return paired


def _extract_labels(result: RaceResult) -> list[int]:
    """Extract binary labels (1 if 1st place, 0 otherwise) for 6 boats."""
    place_map: dict[int, int] = {}
    for b in result.boats:
        if b.racer_place_number is not None:
            place_map[b.racer_boat_number] = b.racer_place_number

    labels = []
    for boat_num in range(1, 7):
        labels.append(1 if place_map.get(boat_num) == 1 else 0)
    return labels


def build_dataset(
    paired_data: list[tuple[RaceProgram, RaceResult]],
) -> tuple[list[list[float]], list[int]]:
    """Convert paired race data into feature matrix and labels.

    Returns (X, y) where X is a list of feature vectors and y is binary labels.
    """
    X: list[list[float]] = []
    y: list[int] = []

    for program, result in paired_data:
        features = extract_features(program)
        labels = _extract_labels(result)

        if len(features) != 6 or len(labels) != 6:
            continue

        for feat_dict, label in zip(features, labels):
            row = [feat_dict[name] for name in FEATURE_NAMES]
            X.append(row)
            y.append(label)

    return X, y


def train_model(
    X_train: list[list[float]],
    y_train: list[int],
    X_val: list[list[float]],
    y_val: list[int],
    model_path: Path | None = None,
    meta_path: Path | None = None,
) -> dict:
    """Train a LightGBM model and save it to disk.

    Returns a dict of training metadata (metrics, data size, etc.).
    """
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        raise ImportError(
            "ML機能には lightgbm, numpy が必要です。\n"
            "pip install 'boatrace-ai[ml]' でインストールしてください。"
        )

    save_path = model_path or config.MODEL_PATH
    save_meta = meta_path or config.MODEL_META_PATH

    # Ensure directory exists
    save_path.parent.mkdir(parents=True, exist_ok=True)

    train_data = lgb.Dataset(np.array(X_train), label=np.array(y_train), feature_name=FEATURE_NAMES)
    val_data = lgb.Dataset(np.array(X_val), label=np.array(y_val), feature_name=FEATURE_NAMES, reference=train_data)

    callbacks = [
        lgb.early_stopping(EARLY_STOPPING_ROUNDS),
        lgb.log_evaluation(period=0),  # suppress verbose logging
    ]

    model = lgb.train(
        LGBM_PARAMS,
        train_data,
        num_boost_round=N_ESTIMATORS,
        valid_sets=[val_data],
        valid_names=["val"],
        callbacks=callbacks,
    )

    # Save model
    model.save_model(str(save_path))

    # Evaluate on validation set
    val_preds = model.predict(np.array(X_val))
    metrics = _evaluate(y_val, val_preds)

    # Save metadata
    meta = {
        "trained_at": date.today().isoformat(),
        "train_rows": len(X_train),
        "val_rows": len(X_val),
        "train_races": len(X_train) // 6,
        "val_races": len(X_val) // 6,
        "best_iteration": model.best_iteration,
        "metrics": metrics,
    }
    save_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    log.info("Model saved to %s (best_iteration=%d)", save_path, model.best_iteration)
    return meta


def _evaluate(y_true: list[int], y_pred, num_boats: int = 6) -> dict:
    """Evaluate predictions at the race level.

    Computes:
    - hit_1st_rate: Rate at which the highest-probability boat actually won.
    - hit_top2_rate: Rate at which winner is in top-2 predicted.
    - logloss: Binary log-loss.
    """
    import numpy as np
    from sklearn.metrics import log_loss

    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)

    # Reshape into (num_races, 6)
    num_rows = len(y_true)
    if num_rows % num_boats != 0:
        return {"logloss": float(log_loss(y_true_arr, y_pred_arr))}

    num_races = num_rows // num_boats
    true_matrix = y_true_arr.reshape(num_races, num_boats)
    pred_matrix = y_pred_arr.reshape(num_races, num_boats)

    hit_1st = 0
    hit_top2 = 0
    for i in range(num_races):
        pred_order = np.argsort(-pred_matrix[i])  # indices of boats sorted by pred prob
        actual_winner_idx = np.argmax(true_matrix[i])  # index of actual 1st place boat

        if pred_order[0] == actual_winner_idx:
            hit_1st += 1
        if actual_winner_idx in pred_order[:2]:
            hit_top2 += 1

    return {
        "logloss": round(float(log_loss(y_true_arr, y_pred_arr)), 4),
        "hit_1st_rate": round(hit_1st / num_races, 4) if num_races > 0 else 0.0,
        "hit_top2_rate": round(hit_top2 / num_races, 4) if num_races > 0 else 0.0,
        "num_races": num_races,
    }


def time_series_split(
    paired_data: list[tuple[RaceProgram, RaceResult]],
    val_days: int = 14,
) -> tuple[list[tuple[RaceProgram, RaceResult]], list[tuple[RaceProgram, RaceResult]]]:
    """Split paired data into train and validation sets by date.

    The most recent val_days days become validation; the rest is training.
    This prevents future data leakage.
    """
    # Sort by date
    sorted_data = sorted(paired_data, key=lambda x: x[0].race_date)

    if not sorted_data:
        return [], []

    # Find cutoff date
    all_dates = sorted(set(p.race_date for p, _ in sorted_data))
    if len(all_dates) <= val_days:
        # Not enough data for split: use all for training, empty validation
        return sorted_data, []

    cutoff_date = all_dates[-val_days]

    train = [(p, r) for p, r in sorted_data if p.race_date < cutoff_date]
    val = [(p, r) for p, r in sorted_data if p.race_date >= cutoff_date]

    return train, val
