"""SQLite database operations."""

from __future__ import annotations

import json
import logging
import sqlite3
from importlib import resources

from boatrace_ai import config
from boatrace_ai.data.models import PredictionResult, RaceResult

log = logging.getLogger(__name__)


def _get_connection() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    schema = resources.files("boatrace_ai.storage").joinpath("schema.sql").read_text()
    conn = _get_connection()
    conn.executescript(schema)
    conn.close()


def save_prediction(
    race_date: str,
    stadium_number: int,
    race_number: int,
    prediction: PredictionResult,
) -> None:
    """Save a prediction, replacing any existing one for the same race."""
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO predictions
               (race_date, stadium_number, race_number,
                predicted_order, confidence, recommended_bets, analysis)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                race_date,
                stadium_number,
                race_number,
                json.dumps(prediction.predicted_order),
                prediction.confidence,
                json.dumps(prediction.recommended_bets),
                prediction.analysis,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_result(race_date: str, result: RaceResult) -> None:
    """Save a race result."""
    finished = [b for b in result.boats if b.racer_place_number is not None]
    finished.sort(key=lambda b: b.racer_place_number)  # type: ignore[arg-type]
    actual_order = [b.racer_boat_number for b in finished]

    conn = _get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO results
               (race_date, stadium_number, race_number,
                actual_order, weather_number, wind, wind_direction_number,
                wave, temperature, water_temperature, technique_number, payouts_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                race_date,
                result.race_stadium_number,
                result.race_number,
                json.dumps(actual_order) if actual_order else None,
                result.race_weather_number,
                result.race_wind,
                result.race_wind_direction_number,
                result.race_wave,
                result.race_temperature,
                result.race_water_temperature,
                result.race_technique_number,
                result.payouts.model_dump_json(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def check_accuracy() -> list[dict]:
    """Compare predictions with results and update accuracy_log.

    Returns list of accuracy records. Wrapped in a transaction for atomicity.
    """
    conn = _get_connection()

    try:
        rows = conn.execute(
            """SELECT p.race_date, p.stadium_number, p.race_number,
                      p.predicted_order, r.actual_order
               FROM predictions p
               JOIN results r
                 ON p.race_date = r.race_date
                AND p.stadium_number = r.stadium_number
                AND p.race_number = r.race_number
               WHERE r.actual_order IS NOT NULL
                 AND NOT EXISTS (
                   SELECT 1 FROM accuracy_log a
                   WHERE a.race_date = p.race_date
                     AND a.stadium_number = p.stadium_number
                     AND a.race_number = p.race_number
                 )"""
        ).fetchall()

        records = []
        for row in rows:
            try:
                predicted = json.loads(row["predicted_order"])
                actual = json.loads(row["actual_order"])
            except (json.JSONDecodeError, TypeError) as e:
                log.warning(
                    "Skipping %s stadium=%d race=%d: corrupted JSON: %s",
                    row["race_date"], row["stadium_number"], row["race_number"], e,
                )
                continue

            # Guard against empty or short lists (cancelled/disqualified races)
            if not predicted or not actual:
                log.warning(
                    "Skipping %s stadium=%d race=%d: empty order data",
                    row["race_date"], row["stadium_number"], row["race_number"],
                )
                continue

            predicted_1st = predicted[0]
            actual_1st = actual[0]
            hit_1st = 1 if predicted_1st == actual_1st else 0

            # Trifecta: need at least 3 finishers
            predicted_tri = "-".join(str(x) for x in predicted[:3]) if len(predicted) >= 3 else ""
            actual_tri = "-".join(str(x) for x in actual[:3]) if len(actual) >= 3 else ""
            hit_tri = 1 if predicted_tri and actual_tri and predicted_tri == actual_tri else 0

            conn.execute(
                """INSERT OR REPLACE INTO accuracy_log
                   (race_date, stadium_number, race_number,
                    predicted_1st, actual_1st, hit_1st,
                    predicted_trifecta, actual_trifecta, hit_trifecta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["race_date"],
                    row["stadium_number"],
                    row["race_number"],
                    predicted_1st,
                    actual_1st,
                    hit_1st,
                    predicted_tri,
                    actual_tri,
                    hit_tri,
                ),
            )

            records.append(
                {
                    "race_date": row["race_date"],
                    "stadium_number": row["stadium_number"],
                    "race_number": row["race_number"],
                    "predicted_1st": predicted_1st,
                    "actual_1st": actual_1st,
                    "hit_1st": bool(hit_1st),
                    "predicted_trifecta": predicted_tri,
                    "actual_trifecta": actual_tri,
                    "hit_trifecta": bool(hit_tri),
                }
            )

        conn.commit()
        return records
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_stats() -> dict:
    """Get accuracy statistics from the accuracy_log."""
    conn = _get_connection()
    try:
        row = conn.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(hit_1st) as hit_1st_count,
                 SUM(hit_trifecta) as hit_trifecta_count
               FROM accuracy_log"""
        ).fetchone()

        total = row["total"] if row["total"] else 0
        hit_1st = row["hit_1st_count"] if row["hit_1st_count"] else 0
        hit_tri = row["hit_trifecta_count"] if row["hit_trifecta_count"] else 0

        return {
            "total_races": total,
            "hit_1st": hit_1st,
            "hit_1st_rate": hit_1st / total if total > 0 else 0.0,
            "hit_trifecta": hit_tri,
            "hit_trifecta_rate": hit_tri / total if total > 0 else 0.0,
        }
    finally:
        conn.close()


def get_predictions_for_date(race_date: str) -> list[dict]:
    """Get all predictions for a given date."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE race_date = ? ORDER BY stadium_number, race_number",
            (race_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
