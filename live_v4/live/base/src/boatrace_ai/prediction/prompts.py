"""Prompt templates for Claude API race prediction."""

from __future__ import annotations

from boatrace_ai.data.constants import GRADES, RACER_CLASSES, STADIUMS
from boatrace_ai.data.models import RaceProgram

SYSTEM_PROMPT = """\
あなたは競艇（ボートレース）の予想AIです。豊富なデータ分析に基づき、レース結果を予測します。

## 競艇の基礎知識

- 6艇で争われ、1号艇（白）〜6号艇（緑）のインコースからスタート
- **1コース（イン）の1着率は全国平均55%前後**と圧倒的に有利
- コース別1着率目安: 1コース55% > 2コース15% > 3コース12% > 4コース11% > 5コース5% > 6コース2%
- スタートタイミングが速い選手ほど有利（0に近いほど良い）
- モーター2連率が40%以上なら好モーター、30%以下は低調
- A1級 > A2級 > B1級 > B2級（級別が高いほど実力上位）
- 全国勝率（top_1_percent）が高いほど安定した実力がある
- 当地勝率（local_top_1_percent）はその競艇場との相性を示す

## 予測の手順

1. まず1号艇の選手データを確認（級別・勝率・モーター）
2. 各コースの選手の実力を比較
3. スタートタイミング・モーター性能を加味
4. 展開を予測し、着順を決定
5. 信頼度を設定（堅いレースなら高め、混戦なら低め）
6. 推奨買い目を提案

## 重要な注意

- 必ず submit_prediction ツールを使って予測を返すこと
- 分析は日本語で簡潔に記述すること
"""


def format_race_for_prompt(race: RaceProgram) -> str:
    """Format a race program into a human-readable string for the prompt."""
    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    grade = GRADES.get(race.race_grade_number, "")

    lines = [
        f"## {stadium} {race.race_number}R {grade} {race.race_subtitle}",
        f"レース名: {race.race_title}",
        f"締切: {race.race_closed_at}",
        "",
        "| 枠 | 選手名 | 登番 | 級別 | 全国勝率 | 全国2連率 | 当地勝率 | 当地2連率 | ST平均 | F数 | モーター | モ2連率 | ボート2連率 |",
        "|-----|--------|------|------|----------|-----------|----------|-----------|--------|-----|----------|---------|-------------|",
    ]

    for b in race.boats:
        cls = RACER_CLASSES.get(b.racer_class_number, "?")
        st = f"{b.racer_average_start_timing:.2f}" if b.racer_average_start_timing is not None else "-"
        lines.append(
            f"| {b.racer_boat_number} | {b.racer_name} | {b.racer_number} | {cls} "
            f"| {b.racer_national_top_1_percent:.1f}% | {b.racer_national_top_2_percent:.1f}% "
            f"| {b.racer_local_top_1_percent:.1f}% | {b.racer_local_top_2_percent:.1f}% "
            f"| {st} | {b.racer_flying_count} "
            f"| No.{b.racer_assigned_motor_number} | {b.racer_assigned_motor_top_2_percent:.1f}% "
            f"| {b.racer_assigned_boat_top_2_percent:.1f}% |"
        )

    return "\n".join(lines)


ANALYSIS_SYSTEM_PROMPT = """\
あなたは競艇予想の解説者です。
AIモデルの予測結果が与えられます。出走表データから予測の根拠を読み解き、
レース展開予測を日本語で簡潔に解説してください。

## 解説のポイント
- なぜその艇が有利なのか（コース・モーター・勝率等）
- スタート展開の予測
- 穴目があるとすればどのパターンか
- 200字程度で簡潔に
"""


def format_ml_result_for_prompt(
    race: RaceProgram,
    predicted_order: list[int],
    probabilities: dict[int, float],
) -> str:
    """Format ML prediction results for the analysis prompt."""
    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    grade = GRADES.get(race.race_grade_number, "")

    lines = [
        f"## {stadium} {race.race_number}R {grade} {race.race_subtitle}",
        "",
        "### AI予測結果",
        f"予測着順: {' → '.join(str(n) for n in predicted_order)}",
        "",
        "### 各艇の勝率予測",
    ]
    for bn in predicted_order:
        lines.append(f"  {bn}号艇: {probabilities.get(bn, 0):.1%}")

    lines.append("")
    lines.append("### 出走表")

    race_text = format_race_for_prompt(race)
    # Skip the header lines already added
    for line in race_text.split("\n")[1:]:
        lines.append(line)

    return "\n".join(lines)


ANALYSIS_TOOL = {
    "name": "submit_analysis",
    "description": "レース展開予測の解説を提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": "日本語での解説。レース展開予測、注目ポイント等を200字程度で簡潔に記述",
            },
        },
        "required": ["analysis"],
    },
}


# tool_use schema for structured prediction output
PREDICTION_TOOL = {
    "name": "submit_prediction",
    "description": "レース予測結果を構造化データとして提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "predicted_order": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 6,
                "maxItems": 6,
                "description": "予測着順。1着から6着までのボート番号をリストで指定。例: [1, 3, 2, 5, 4, 6]",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "予測の信頼度 (0.0〜1.0)。堅いレースなら0.7以上、混戦なら0.3以下",
            },
            "recommended_bets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "推奨買い目リスト。例: ['3連単 1-3-2', '2連単 1-3', '3連複 1=2=3']",
            },
            "analysis": {
                "type": "string",
                "description": "日本語での分析コメント。レース展開予測、注目ポイント等を簡潔に記述",
            },
        },
        "required": ["predicted_order", "confidence", "recommended_bets", "analysis"],
    },
}
