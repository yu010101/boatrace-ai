"""Feature extraction from RaceProgram for ML prediction.

29 features per boat x 6 boats = 174 dimensions per race.
Each boat produces one row; a race produces 6 rows.
"""

from __future__ import annotations

from boatrace_ai.data.models import RaceProgram


# Feature names in stable order (used by model training and prediction)
FEATURE_NAMES: list[str] = [
    # Raw features (18)
    "boat_number",
    "class_number",
    "age",
    "weight",
    "flying_count",
    "late_count",
    "avg_start_timing",
    "is_null_st",
    "national_top1_pct",
    "national_top2_pct",
    "national_top3_pct",
    "local_top1_pct",
    "local_top2_pct",
    "local_top3_pct",
    "motor_top2_pct",
    "motor_top3_pct",
    "boat_top2_pct",
    "boat_top3_pct",
    # Relative features (7)
    "national_top1_rank",
    "local_top1_rank",
    "motor_top2_rank",
    "avg_st_rank",
    "national_top1_diff_from_mean",
    "motor_top2_diff_from_mean",
    "class_is_best_in_race",
    # Race context (4)
    "stadium_number",
    "grade_number",
    "race_distance",
    "branch_number",
]

DEFAULT_ST = 0.20  # Default start timing when null


def _rank_values(values: list[float], ascending: bool = True) -> list[int]:
    """Rank values 1..N. ascending=True means smallest value gets rank 1."""
    indexed = sorted(enumerate(values), key=lambda x: x[1], reverse=not ascending)
    ranks = [0] * len(values)
    for rank, (idx, _) in enumerate(indexed, 1):
        ranks[idx] = rank
    return ranks


def extract_features(race: RaceProgram) -> list[dict[str, float]]:
    """Extract feature vectors for all 6 boats in a race.

    Returns a list of 6 dicts, each mapping feature name -> value.
    """
    boats = sorted(race.boats, key=lambda b: b.racer_boat_number)

    # Collect per-boat raw values for relative feature computation
    national_top1_vals = [b.racer_national_top_1_percent for b in boats]
    local_top1_vals = [b.racer_local_top_1_percent for b in boats]
    motor_top2_vals = [b.racer_assigned_motor_top_2_percent for b in boats]
    st_vals = [
        b.racer_average_start_timing if b.racer_average_start_timing is not None else DEFAULT_ST
        for b in boats
    ]
    class_vals = [b.racer_class_number for b in boats]

    # Compute ranks (lower rank = better)
    national_top1_ranks = _rank_values(national_top1_vals, ascending=False)  # higher % = rank 1
    local_top1_ranks = _rank_values(local_top1_vals, ascending=False)
    motor_top2_ranks = _rank_values(motor_top2_vals, ascending=False)
    avg_st_ranks = _rank_values(st_vals, ascending=True)  # lower ST = rank 1

    # Means for diff features
    national_top1_mean = sum(national_top1_vals) / len(national_top1_vals)
    motor_top2_mean = sum(motor_top2_vals) / len(motor_top2_vals)

    # Best class in race (lowest class_number = highest rank)
    best_class = min(class_vals)

    rows: list[dict[str, float]] = []
    for i, b in enumerate(boats):
        st = b.racer_average_start_timing if b.racer_average_start_timing is not None else DEFAULT_ST
        is_null_st = 1.0 if b.racer_average_start_timing is None else 0.0

        row = {
            # Raw features
            "boat_number": float(b.racer_boat_number),
            "class_number": float(b.racer_class_number),
            "age": float(b.racer_age),
            "weight": float(b.racer_weight),
            "flying_count": float(b.racer_flying_count),
            "late_count": float(b.racer_late_count),
            "avg_start_timing": float(st),
            "is_null_st": is_null_st,
            "national_top1_pct": float(b.racer_national_top_1_percent),
            "national_top2_pct": float(b.racer_national_top_2_percent),
            "national_top3_pct": float(b.racer_national_top_3_percent),
            "local_top1_pct": float(b.racer_local_top_1_percent),
            "local_top2_pct": float(b.racer_local_top_2_percent),
            "local_top3_pct": float(b.racer_local_top_3_percent),
            "motor_top2_pct": float(b.racer_assigned_motor_top_2_percent),
            "motor_top3_pct": float(b.racer_assigned_motor_top_3_percent),
            "boat_top2_pct": float(b.racer_assigned_boat_top_2_percent),
            "boat_top3_pct": float(b.racer_assigned_boat_top_3_percent),
            # Relative features
            "national_top1_rank": float(national_top1_ranks[i]),
            "local_top1_rank": float(local_top1_ranks[i]),
            "motor_top2_rank": float(motor_top2_ranks[i]),
            "avg_st_rank": float(avg_st_ranks[i]),
            "national_top1_diff_from_mean": float(b.racer_national_top_1_percent - national_top1_mean),
            "motor_top2_diff_from_mean": float(b.racer_assigned_motor_top_2_percent - motor_top2_mean),
            "class_is_best_in_race": 1.0 if b.racer_class_number == best_class else 0.0,
            # Race context
            "stadium_number": float(race.race_stadium_number),
            "grade_number": float(race.race_grade_number),
            "race_distance": float(race.race_distance),
            "branch_number": float(b.racer_branch_number),
        }
        rows.append(row)

    return rows
