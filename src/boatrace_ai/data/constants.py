"""Boat race constants: stadium names, racer classes, weather codes, etc."""

from __future__ import annotations

# 競艇場（24場）: stadium_number -> name
STADIUMS: dict[int, str] = {
    1: "桐生",
    2: "戸田",
    3: "江戸川",
    4: "平和島",
    5: "多摩川",
    6: "浜名湖",
    7: "蒲郡",
    8: "常滑",
    9: "津",
    10: "三国",
    11: "びわこ",
    12: "住之江",
    13: "尼崎",
    14: "鳴門",
    15: "丸亀",
    16: "児島",
    17: "宮島",
    18: "徳山",
    19: "下関",
    20: "若松",
    21: "芦屋",
    22: "福岡",
    23: "唐津",
    24: "大村",
}

# 選手級別: class_number -> label
RACER_CLASSES: dict[int, str] = {
    1: "A1",
    2: "A2",
    3: "B1",
    4: "B2",
}

# 支部: branch_number -> name
BRANCHES: dict[int, str] = {
    1: "群馬",
    2: "埼玉",
    3: "東京",
    4: "静岡",
    5: "愛知",
    6: "三重",
    7: "福井",
    8: "滋賀",
    9: "大阪",
    10: "兵庫",
    11: "徳島",
    12: "香川",
    13: "岡山",
    14: "広島",
    15: "山口",
    16: "福岡",
    17: "佐賀",
    18: "長崎",
    19: "熊本",
    20: "大分",
    21: "宮崎",
    22: "鹿児島",
    23: "沖縄",
    24: "長野",
    25: "岐阜",
    26: "新潟",
    27: "富山",
    28: "石川",
}

# 天候: weather_number -> label
WEATHER: dict[int, str] = {
    1: "晴",
    2: "曇り",
    3: "雨",
    4: "雪",
    5: "霧",
}

# 決まり手: technique_number -> label
TECHNIQUES: dict[int, str] = {
    1: "逃げ",
    2: "差し",
    3: "まくり",
    4: "まくり差し",
    5: "抜き",
    6: "恵まれ",
}

# 風向: wind_direction_number -> label (16方位)
WIND_DIRECTIONS: dict[int, str] = {
    1: "北",
    2: "北北東",
    3: "北東",
    4: "東北東",
    5: "東",
    6: "東南東",
    7: "南東",
    8: "南南東",
    9: "南",
    10: "南南西",
    11: "南西",
    12: "西南西",
    13: "西",
    14: "西北西",
    15: "北西",
    16: "北北西",
}

# グレード: grade_number -> label
GRADES: dict[int, str] = {
    1: "SG",
    2: "G1",
    3: "G2",
    4: "G3",
    5: "一般",
}
