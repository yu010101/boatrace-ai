"""Feature extraction from RaceProgram for ML prediction.

35 features per boat x 6 boats = 210 dimensions per race.
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
    # Pairwise features (4)
    "inner_national_top1_diff",
    "inner_motor_top2_diff",
    "top2_national_gap",
    "top2_motor_gap",
    # Race context (6)
    "stadium_number",
    "grade_number",
    "race_distance",
    "branch_number",
    "stadium_inner_win_rate",
    "is_inner_boat",
]

# Categorical feature names for LightGBM (treated as discrete categories, not numeric)
CATEGORICAL_FEATURES: list[str] = [
    "stadium_number",
    "grade_number",
    "branch_number",
]

# Historical 1-course win rate per stadium (公式データ 2023-2024 平均)
# Source: boatrace.jp コース別入着率
STADIUM_INNER_WIN_RATE: dict[int, float] = {
    1: 0.52,   # 桐生
    2: 0.45,   # 戸田
    3: 0.44,   # 江戸川
    4: 0.47,   # 平和島
    5: 0.51,   # 多摩川
    6: 0.54,   # 浜名湖
    7: 0.53,   # 蒲郡
    8: 0.55,   # 常滑
    9: 0.54,   # 津
    10: 0.51,  # 三国
    11: 0.51,  # びわこ
    12: 0.55,  # 住之江
    13: 0.54,  # 尼崎
    14: 0.53,  # 鳴門
    15: 0.56,  # 丸亀
    16: 0.53,  # 児島
    17: 0.56,  # 宮島
    18: 0.59,  # 徳山
    19: 0.56,  # 下関
    20: 0.55,  # 若松
    21: 0.61,  # 芦屋
    22: 0.50,  # 福岡
    23: 0.55,  # 唐津
    24: 0.65,  # 大村
}

DEFAULT_ST = 0.20  # Default start timing when null
DEFAULT_INNER_WIN_RATE = 0.54  # Fallback for unknown stadiums


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

    # Inner boat (boat 1) values for pairwise comparison
    inner_national = national_top1_vals[0]  # boat 1
    inner_motor = motor_top2_vals[0]

    # Top-2 gap: difference between best and second-best
    sorted_national = sorted(national_top1_vals, reverse=True)
    sorted_motor = sorted(motor_top2_vals, reverse=True)
    top2_national_gap = sorted_national[0] - sorted_national[1]
    top2_motor_gap = sorted_motor[0] - sorted_motor[1]

    # Stadium inner win rate
    inner_win_rate = STADIUM_INNER_WIN_RATE.get(
        race.race_stadium_number, DEFAULT_INNER_WIN_RATE
    )

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
            # Pairwise features
            "inner_national_top1_diff": float(b.racer_national_top_1_percent - inner_national),
            "inner_motor_top2_diff": float(b.racer_assigned_motor_top_2_percent - inner_motor),
            "top2_national_gap": float(top2_national_gap),
            "top2_motor_gap": float(top2_motor_gap),
            # Race context
            "stadium_number": float(race.race_stadium_number),
            "grade_number": float(race.race_grade_number),
            "race_distance": float(race.race_distance),
            "branch_number": float(b.racer_branch_number),
            "stadium_inner_win_rate": float(inner_win_rate),
            "is_inner_boat": 1.0 if b.racer_boat_number == 1 else 0.0,
        }
        rows.append(row)

    return rows
