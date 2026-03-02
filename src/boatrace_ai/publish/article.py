"""Generate note.com articles from race predictions.

note.com's ProseMirror editor supports: <h2>, <h3>, <p>, <strong>, <ul><li>, <hr>.
It does NOT support: <h1>, <table>, <blockquote>, <code>.
We generate note.com-compatible HTML directly (no Markdown→HTML conversion).
"""

from __future__ import annotations

from boatrace_ai.data.constants import RACER_CLASSES, STADIUMS
from boatrace_ai.data.models import PredictionResult, RaceProgram

AccuracyRecord = dict  # type alias for readability

DISCLAIMER = (
    "この予測はAI（Claude）による統計分析に基づくものです。"
    "的中を保証するものではありません。舟券の購入は自己責任でお願いします。"
)


def _build_html(
    race: RaceProgram,
    prediction: PredictionResult,
    *,
    free: bool = False,
    grade: str | None = None,
) -> str:
    """Build note.com-compatible HTML with free/paid sections.

    Args:
        free: If True, omit <pay> tag, paywall text, and include all content as free.
        grade: Optional race grade (S/A/B/C) to include in the article.
    """
    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    boat_map = {b.racer_boat_number: b for b in race.boats}
    top3 = prediction.predicted_order[:3]
    confidence_pct = int(prediction.confidence * 100)

    parts: list[str] = []

    # ── Free section ──
    grade_label = f"【推奨度{grade}】" if grade else "🏁 "
    parts.append(f"<h2>{grade_label}{stadium}競艇 第{race.race_number}R AI予測｜{race.race_date}</h2>")

    parts.append("<h3>予測着順</h3>")
    for i, boat_num in enumerate(top3, 1):
        boat = boat_map.get(boat_num)
        name = boat.racer_name if boat else "?"
        parts.append(f"<p><strong>{i}着: {boat_num}号艇</strong>（{name}）</p>")

    parts.append(f"<p><strong>信頼度: {confidence_pct}%</strong></p>")

    parts.append("<h3>推奨買い目</h3>")
    bets_html = "".join(f"<li>{bet}</li>" for bet in prediction.recommended_bets)
    parts.append(f"<ul>{bets_html}</ul>")

    if not free:
        parts.append("<hr>")
        parts.append("<p>↓ 詳細分析は有料エリア ↓</p>")

        # ── Pay wall ──
        parts.append("<pay>")

    # ── Detail section (paid when not free, always included) ──
    parts.append("<h2>AI詳細分析</h2>")
    parts.append(f"<p>{prediction.analysis}</p>")

    # Race data — each boat as a formatted <p> line
    parts.append("<h2>出走表データ</h2>")
    for boat in race.boats:
        cls = RACER_CLASSES.get(boat.racer_class_number, "?")
        st = (
            f"{boat.racer_average_start_timing:.2f}"
            if boat.racer_average_start_timing is not None
            else "-"
        )
        parts.append(
            f"<p>"
            f"<strong>{boat.racer_boat_number}号艇</strong>｜"
            f"{boat.racer_name}｜{cls}｜"
            f"全国 {boat.racer_national_top_1_percent:.1f}%｜"
            f"当地 {boat.racer_local_top_1_percent:.1f}%｜"
            f"ST {st}｜"
            f"モーター {boat.racer_assigned_motor_top_2_percent:.1f}%｜"
            f"ボート {boat.racer_assigned_boat_top_2_percent:.1f}%"
            f"</p>"
        )

    # Full predicted order
    parts.append("<h3>全着順予測</h3>")
    order_str = " → ".join(str(n) for n in prediction.predicted_order)
    parts.append(f"<p>{order_str}</p>")

    # Disclaimer
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    return "\n".join(parts)


def _build_markdown(
    race: RaceProgram,
    prediction: PredictionResult,
    *,
    free: bool = False,
    grade: str | None = None,
) -> str:
    """Build Markdown preview for CLI dry-run display."""
    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    boat_map = {b.racer_boat_number: b for b in race.boats}
    top3 = prediction.predicted_order[:3]
    confidence_pct = int(prediction.confidence * 100)

    lines: list[str] = []

    grade_label = f"【推奨度{grade}】" if grade else "🏁 "
    lines.append(f"## {grade_label}{stadium}競艇 第{race.race_number}R AI予測｜{race.race_date}")
    lines.append("")
    lines.append("### 予測着順")
    for i, boat_num in enumerate(top3, 1):
        boat = boat_map.get(boat_num)
        name = boat.racer_name if boat else "?"
        lines.append(f"**{i}着: {boat_num}号艇**（{name}）")
        lines.append("")
    lines.append(f"**信頼度: {confidence_pct}%**")
    lines.append("")
    lines.append("### 推奨買い目")
    for bet in prediction.recommended_bets:
        lines.append(f"- {bet}")
    lines.append("")

    if not free:
        lines.append("---")
        lines.append("↓ 詳細分析は有料エリア ↓")
        lines.append("")

    lines.append("## AI詳細分析")
    lines.append(prediction.analysis)
    lines.append("")

    lines.append("## 出走表データ")
    for boat in race.boats:
        cls = RACER_CLASSES.get(boat.racer_class_number, "?")
        st = f"{boat.racer_average_start_timing:.2f}" if boat.racer_average_start_timing is not None else "-"
        lines.append(
            f"**{boat.racer_boat_number}号艇**｜{boat.racer_name}｜{cls}｜"
            f"全国 {boat.racer_national_top_1_percent:.1f}%｜"
            f"当地 {boat.racer_local_top_1_percent:.1f}%｜"
            f"ST {st}｜"
            f"モーター {boat.racer_assigned_motor_top_2_percent:.1f}%｜"
            f"ボート {boat.racer_assigned_boat_top_2_percent:.1f}%"
        )
        lines.append("")

    lines.append("### 全着順予測")
    order_str = " → ".join(str(n) for n in prediction.predicted_order)
    lines.append(order_str)
    lines.append("")
    lines.append("### 注意事項")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


def _build_hashtags(race: RaceProgram) -> list[str]:
    """Generate hashtags for the article."""
    stadium = STADIUMS.get(race.race_stadium_number, "")
    tags = ["競艇", "ボートレース", "AI予測"]
    if stadium:
        tags.append(stadium)
    return tags


def generate_article(
    race: RaceProgram,
    prediction: PredictionResult,
    *,
    free: bool = False,
    grade: str | None = None,
) -> tuple[str, str, list[str]]:
    """Generate a note.com article from race data and prediction.

    Args:
        race: The race program data
        prediction: The AI prediction result
        free: If True, generate as free article (no paywall)
        grade: Optional race grade (S/A/B/C) to include in title

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    stadium = STADIUMS.get(race.race_stadium_number, f"場{race.race_stadium_number}")
    if grade:
        title = f"【推奨度{grade}】{stadium}競艇 第{race.race_number}R AI予測｜{race.race_date}"
    else:
        title = f"{stadium}競艇 第{race.race_number}R AI予測｜{race.race_date}"

    html_body = _build_html(race, prediction, free=free, grade=grade)
    hashtags = _build_hashtags(race)

    return title, html_body, hashtags


# ── Accuracy report ──────────────────────────────────────────


def _build_accuracy_html(
    race_date: str,
    records: list[AccuracyRecord],
    stats: dict,
    roi_stats: dict | None = None,
) -> str:
    """Build note.com-compatible HTML for accuracy report."""
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_tri = sum(1 for r in records if r["hit_trifecta"])
    hit_1st_pct = int(hit_1st / total * 100) if total else 0
    hit_tri_pct = int(hit_tri / total * 100) if total else 0

    parts: list[str] = []

    parts.append(f"<h2>📊 AI予測 結果レポート｜{race_date}</h2>")
    parts.append(f"<p><strong>1着的中率: {hit_1st_pct}% ({hit_1st}/{total})</strong></p>")
    parts.append(f"<p><strong>3連単的中率: {hit_tri_pct}% ({hit_tri}/{total})</strong></p>")

    # Hit races
    hits = [r for r in records if r["hit_1st"] or r["hit_trifecta"]]
    if hits:
        parts.append("<h3>的中レース ✅</h3>")
        for r in hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            if r["hit_trifecta"]:
                parts.append(
                    f"<p>✅ {stadium} {r['race_number']}R — "
                    f"予測: {r['predicted_trifecta']} → "
                    f"実際: {r['actual_trifecta']}（3連単的中!）</p>"
                )
            else:
                parts.append(
                    f"<p>✅ {stadium} {r['race_number']}R — "
                    f"予測1着: {r['predicted_1st']} → "
                    f"実際1着: {r['actual_1st']}</p>"
                )

    # Miss races
    misses = [r for r in records if not r["hit_1st"] and not r["hit_trifecta"]]
    if misses:
        parts.append("<h3>不的中レース</h3>")
        for r in misses:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            parts.append(
                f"<p>❌ {stadium} {r['race_number']}R — "
                f"予測: {r['predicted_trifecta']} → "
                f"実際: {r['actual_trifecta']}</p>"
            )

    # ROI section
    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = int(roi_stats["roi"] * 100)
        profit = roi_stats["profit"]
        parts.append("<h3>回収率</h3>")
        parts.append(
            f"<p><strong>回収率: {roi_pct}%</strong>"
            f"（投資 ¥{roi_stats['total_invested']:,}"
            f" → 払戻 ¥{roi_stats['total_payout']:,}"
            f" / 損益 ¥{profit:+,}）</p>"
        )

    # Cumulative stats
    parts.append("<h3>累計成績</h3>")
    cum_total = stats["total_races"]
    cum_1st_pct = int(stats["hit_1st_rate"] * 100)
    cum_tri_pct = int(stats["hit_trifecta_rate"] * 100)
    parts.append(
        f"<p>総レース: {cum_total} | "
        f"1着的中率: {cum_1st_pct}% | "
        f"3連単的中率: {cum_tri_pct}%</p>"
    )

    # Disclaimer
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    return "\n".join(parts)


def _build_accuracy_markdown(
    race_date: str,
    records: list[AccuracyRecord],
    stats: dict,
    roi_stats: dict | None = None,
) -> str:
    """Build Markdown preview for accuracy report."""
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_tri = sum(1 for r in records if r["hit_trifecta"])
    hit_1st_pct = int(hit_1st / total * 100) if total else 0
    hit_tri_pct = int(hit_tri / total * 100) if total else 0

    lines: list[str] = []

    lines.append(f"## 📊 AI予測 結果レポート｜{race_date}")
    lines.append("")
    lines.append(f"**1着的中率: {hit_1st_pct}% ({hit_1st}/{total})**")
    lines.append("")
    lines.append(f"**3連単的中率: {hit_tri_pct}% ({hit_tri}/{total})**")
    lines.append("")

    # Hit races
    hits = [r for r in records if r["hit_1st"] or r["hit_trifecta"]]
    if hits:
        lines.append("### 的中レース ✅")
        lines.append("")
        for r in hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            if r["hit_trifecta"]:
                lines.append(
                    f"✅ {stadium} {r['race_number']}R — "
                    f"予測: {r['predicted_trifecta']} → "
                    f"実際: {r['actual_trifecta']}（3連単的中!）"
                )
            else:
                lines.append(
                    f"✅ {stadium} {r['race_number']}R — "
                    f"予測1着: {r['predicted_1st']} → "
                    f"実際1着: {r['actual_1st']}"
                )
            lines.append("")

    # Miss races
    misses = [r for r in records if not r["hit_1st"] and not r["hit_trifecta"]]
    if misses:
        lines.append("### 不的中レース")
        lines.append("")
        for r in misses:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            lines.append(
                f"❌ {stadium} {r['race_number']}R — "
                f"予測: {r['predicted_trifecta']} → "
                f"実際: {r['actual_trifecta']}"
            )
            lines.append("")

    # ROI section
    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = int(roi_stats["roi"] * 100)
        profit = roi_stats["profit"]
        lines.append("### 回収率")
        lines.append("")
        lines.append(
            f"**回収率: {roi_pct}%**"
            f"（投資 ¥{roi_stats['total_invested']:,}"
            f" → 払戻 ¥{roi_stats['total_payout']:,}"
            f" / 損益 ¥{profit:+,}）"
        )
        lines.append("")

    # Cumulative stats
    lines.append("### 累計成績")
    lines.append("")
    cum_total = stats["total_races"]
    cum_1st_pct = int(stats["hit_1st_rate"] * 100)
    cum_tri_pct = int(stats["hit_trifecta_rate"] * 100)
    lines.append(
        f"総レース: {cum_total} | "
        f"1着的中率: {cum_1st_pct}% | "
        f"3連単的中率: {cum_tri_pct}%"
    )

    return "\n".join(lines)


def generate_accuracy_report(
    race_date: str,
    records: list[AccuracyRecord],
    stats: dict,
    roi_stats: dict | None = None,
) -> tuple[str, str, list[str]]:
    """Generate a note.com accuracy report article.

    Args:
        race_date: The date of the races (YYYY-MM-DD)
        records: List of accuracy records from get_accuracy_for_date()
        stats: Cumulative stats from get_stats()
        roi_stats: Optional ROI stats for the date

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    title = f"AI予測 結果レポート｜{race_date}"
    html_body = _build_accuracy_html(race_date, records, stats, roi_stats=roi_stats)
    hashtags = ["競艇", "ボートレース", "AI予測", "的中レポート"]
    return title, html_body, hashtags


# ── Grade summary article ────────────────────────────────────


def generate_grade_summary_article(
    race_date: str,
    grades: list[dict],
) -> tuple[str, str, list[str]]:
    """Generate a free article listing all race grades for the day.

    Args:
        race_date: The date (YYYY-MM-DD)
        grades: List of grade dicts from get_grades_for_date()

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    title = f"【AI予測】本日の推奨度ランク一覧｜{race_date}"

    parts: list[str] = []
    parts.append(f"<h2>📊 本日の推奨度ランク一覧｜{race_date}</h2>")

    s_count = sum(1 for g in grades if g["grade"] == "S")
    a_count = sum(1 for g in grades if g["grade"] == "A")
    parts.append(
        f"<p><strong>全{len(grades)}レース中、Sランク: {s_count} / Aランク: {a_count}</strong></p>"
    )

    for rank in ["S", "A", "B", "C"]:
        rank_grades = [g for g in grades if g["grade"] == rank]
        if not rank_grades:
            continue

        label = {"S": "推奨度S（高確信）", "A": "推奨度A（有力）",
                 "B": "推奨度B（予測可能）", "C": "推奨度C（見送り推奨）"}[rank]
        parts.append(f"<h3>{label}</h3>")

        for g in rank_grades:
            stadium = STADIUMS.get(g["stadium_number"], str(g["stadium_number"]))
            parts.append(
                f"<p><strong>{stadium} {g['race_number']}R</strong>"
                f"（p1={g['top1_prob']:.0%}, top2={g['top2_prob']:.0%}）"
                f"— {g.get('reason', '')}</p>"
            )

    parts.append("<h3>Sランク詳細予測</h3>")
    if s_count > 0:
        parts.append("<p>Sランクの買い目詳細は有料記事で公開しています。</p>")
    else:
        parts.append("<p>本日はSランク該当レースがありません。</p>")

    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)
    hashtags = ["競艇", "ボートレース", "AI予測", "推奨度ランク"]

    return title, html_body, hashtags
