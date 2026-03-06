"""Generate note.com articles from race predictions.

note.com's ProseMirror editor supports: <h2>, <h3>, <p>, <strong>, <ul><li>, <hr>.
It does NOT support: <h1>, <table>, <blockquote>, <code>.
We generate note.com-compatible HTML directly (no Markdown→HTML conversion).
"""

from __future__ import annotations

from collections import defaultdict

from boatrace_ai.data.constants import RACER_CLASSES, STADIUMS
from boatrace_ai.data.models import PredictionResult, RaceProgram

AccuracyRecord = dict  # type alias for readability

DISCLAIMER = (
    "この予測はAI（機械学習モデル）による統計分析に基づくものです。"
    "的中を保証するものではありません。舟券の購入は自己責任でお願いします。"
)

ABOUT_SUIRI_AI = (
    "<h3>水理AIとは</h3>"
    "<p>LightGBMと独自特徴量でボートレース全場を毎朝自動予測するAI。"
    "推奨度ランク・的中率・ROIはすべてデータベースで記録し、嘘なく公開しています。</p>"
)


def _build_hashtags(
    race: RaceProgram | None = None,
    *,
    venue_names: list[str] | None = None,
) -> list[str]:
    """Generate hashtags for the article."""
    tags = ["競艇", "ボートレース", "ボートレース予想", "AI予測", "競艇予想", "水理AI"]
    if race:
        stadium = STADIUMS.get(race.race_stadium_number, "")
        if stadium and stadium not in tags:
            tags.append(stadium)
    if venue_names:
        for name in venue_names:
            if name and name not in tags:
                tags.append(name)
    return tags[:8]


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
    grade_label = f"【推奨度{grade}】" if grade else ""
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

    # Footer
    parts.append(ABOUT_SUIRI_AI)
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

    grade_label = f"【推奨度{grade}】" if grade else ""
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
    lines.append("### 水理AIとは")
    lines.append("LightGBMと独自特徴量でボートレース全場を毎朝自動予測するAI。")
    lines.append("")
    lines.append("### 注意事項")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


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

    # ── Summary ──
    parts.append("<h2>本日の結果サマリー</h2>")
    parts.append(
        f"<p><strong>1着的中: {hit_1st}/{total} ({hit_1st_pct}%) | "
        f"3連単的中: {hit_tri}/{total} ({hit_tri_pct}%)</strong></p>"
    )

    # ROI for the day
    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = int(roi_stats["roi"] * 100)
        profit = roi_stats["profit"]
        parts.append(
            f"<p>本日ROI: {roi_pct}%"
            f"（投資 ¥{roi_stats['total_invested']:,}"
            f" → 払戻 ¥{roi_stats['total_payout']:,}"
            f" / 損益 ¥{profit:+,}）</p>"
        )

    # ── Highlight: trifecta hits ──
    tri_hits = [r for r in records if r["hit_trifecta"]]
    if tri_hits:
        parts.append("<h3>本日のハイライト</h3>")
        for r in tri_hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            parts.append(
                f"<p><strong>{stadium} {r['race_number']}R — 3連単的中!</strong> "
                f"予測: {r['predicted_trifecta']} → 結果: {r['actual_trifecta']}</p>"
            )

    # ── Hit races by venue ──
    first_only_hits = [r for r in records if r["hit_1st"] and not r["hit_trifecta"]]
    if first_only_hits or tri_hits:
        parts.append("<h3>的中レース一覧</h3>")
        all_hits = [r for r in records if r["hit_1st"] or r["hit_trifecta"]]
        by_venue: dict[str, list] = defaultdict(list)
        for r in all_hits:
            venue = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            by_venue[venue].append(r)

        for venue, venue_records in sorted(by_venue.items()):
            race_parts = []
            for r in sorted(venue_records, key=lambda x: x["race_number"]):
                marker = "3連単" if r["hit_trifecta"] else "1着"
                race_parts.append(f"{r['race_number']}R({marker})")
            parts.append(f"<p><strong>{venue}</strong>: {', '.join(race_parts)}</p>")

    # ── Cumulative stats ──
    parts.append("<h3>累計成績</h3>")
    cum_total = stats["total_races"]
    cum_1st_pct = int(stats["hit_1st_rate"] * 100)
    cum_tri_pct = int(stats["hit_trifecta_rate"] * 100)
    parts.append(
        f"<p>総レース: {cum_total} | "
        f"1着的中率: {cum_1st_pct}% | "
        f"3連単的中率: {cum_tri_pct}%</p>"
    )

    # Footer
    parts.append(ABOUT_SUIRI_AI)
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

    lines.append(f"## 本日の結果サマリー")
    lines.append("")
    lines.append(
        f"**1着的中: {hit_1st}/{total} ({hit_1st_pct}%) | "
        f"3連単的中: {hit_tri}/{total} ({hit_tri_pct}%)**"
    )
    lines.append("")

    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = int(roi_stats["roi"] * 100)
        profit = roi_stats["profit"]
        lines.append(
            f"本日ROI: {roi_pct}%"
            f"（投資 ¥{roi_stats['total_invested']:,}"
            f" → 払戻 ¥{roi_stats['total_payout']:,}"
            f" / 損益 ¥{profit:+,}）"
        )
        lines.append("")

    # Highlight
    tri_hits = [r for r in records if r["hit_trifecta"]]
    if tri_hits:
        lines.append("### 本日のハイライト")
        lines.append("")
        for r in tri_hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            lines.append(
                f"**{stadium} {r['race_number']}R — 3連単的中!** "
                f"予測: {r['predicted_trifecta']} → 結果: {r['actual_trifecta']}"
            )
            lines.append("")

    # Hit races by venue
    all_hits = [r for r in records if r["hit_1st"] or r["hit_trifecta"]]
    if all_hits:
        lines.append("### 的中レース一覧")
        lines.append("")
        by_venue: dict[str, list] = defaultdict(list)
        for r in all_hits:
            venue = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            by_venue[venue].append(r)
        for venue, venue_records in sorted(by_venue.items()):
            race_parts = []
            for r in sorted(venue_records, key=lambda x: x["race_number"]):
                marker = "3連単" if r["hit_trifecta"] else "1着"
                race_parts.append(f"{r['race_number']}R({marker})")
            lines.append(f"**{venue}**: {', '.join(race_parts)}")
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
    lines.append("")
    lines.append("### 水理AIとは")
    lines.append("LightGBMと独自特徴量でボートレース全場を毎朝自動予測するAI。")
    lines.append("")
    lines.append("### 注意事項")
    lines.append(DISCLAIMER)

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
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_1st_pct = int(hit_1st / total * 100) if total else 0

    title = f"【{race_date}結果】1着的中率 {hit_1st_pct}% — 水理AI 的中レポート"
    html_body = _build_accuracy_html(race_date, records, stats, roi_stats=roi_stats)

    # Collect venue names for hashtags
    venue_names = []
    for r in records:
        name = STADIUMS.get(r["stadium_number"], "")
        if name and name not in venue_names:
            venue_names.append(name)
    hashtags = _build_hashtags(venue_names=venue_names[:3])

    return title, html_body, hashtags


# ── Grade summary article ────────────────────────────────────


def generate_grade_summary_article(
    race_date: str,
    grades: list[dict],
    stats: dict | None = None,
) -> tuple[str, str, list[str]]:
    """Generate a free article listing all race grades for the day.

    Args:
        race_date: The date (YYYY-MM-DD)
        grades: List of grade dicts from get_grades_for_date()
        stats: Optional cumulative stats from get_stats() for displaying hit rates

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    s_count = sum(1 for g in grades if g["grade"] == "S")
    a_count = sum(1 for g in grades if g["grade"] == "A")

    # Build title with hit rate if stats available
    if stats and stats.get("total_races", 0) > 0:
        hit_1st_pct = int(stats["hit_1st_rate"] * 100)
        title = f"【的中率{hit_1st_pct}%】{race_date} 水理AI 推奨度ランク｜Sランク{s_count}レース"
    else:
        title = f"【AI予測】{race_date} 水理AI 推奨度ランク｜Sランク{s_count}レース"

    parts: list[str] = []

    # ── Summary ──
    parts.append("<h2>本日の予測サマリー</h2>")
    parts.append(
        f"<p>水理AIが全{len(grades)}レースをML分析。"
        f"Sランク{s_count}レース、Aランク{a_count}レースを検出しました。</p>"
    )
    if stats and stats.get("total_races", 0) > 0:
        hit_1st_pct = int(stats["hit_1st_rate"] * 100)
        hit_tri_pct = int(stats["hit_trifecta_rate"] * 100)
        parts.append(
            f"<p><strong>直近の実績: 1着的中率 {hit_1st_pct}% / "
            f"3連単的中率 {hit_tri_pct}%</strong></p>"
        )

    # ── TOP3 注目レース ──
    # Sort S-rank races by top1_prob descending, pick top 3
    s_races = sorted(
        [g for g in grades if g["grade"] == "S"],
        key=lambda g: g["top1_prob"],
        reverse=True,
    )
    if s_races:
        top3 = s_races[:3]
        parts.append("<h3>注目レース TOP3</h3>")
        parts.append("<p>本日最も確信度が高いレースをピックアップ。</p>")
        for g in top3:
            stadium = STADIUMS.get(g["stadium_number"], str(g["stadium_number"]))
            prob_pct = int(g["top1_prob"] * 100)
            parts.append(
                f"<p><strong>{stadium} {g['race_number']}R</strong>: "
                f"本命確率 {prob_pct}%（Sランク）</p>"
            )

    # ── Grades grouped by venue ──
    for rank in ["S", "A", "B", "C"]:
        rank_grades = [g for g in grades if g["grade"] == rank]
        if not rank_grades:
            continue

        label = {
            "S": f"推奨度Sランク（高確信）— {len(rank_grades)}レース",
            "A": f"推奨度Aランク（有力）— {len(rank_grades)}レース",
            "B": f"推奨度Bランク（予測可能）— {len(rank_grades)}レース",
            "C": f"推奨度Cランク（見送り推奨）— {len(rank_grades)}レース",
        }[rank]
        parts.append(f"<h3>{label}</h3>")

        # Group by venue for readability
        by_venue: dict[str, list] = defaultdict(list)
        for g in rank_grades:
            venue = STADIUMS.get(g["stadium_number"], str(g["stadium_number"]))
            by_venue[venue].append(g)

        for venue, venue_grades in sorted(by_venue.items()):
            race_parts = []
            for g in sorted(venue_grades, key=lambda x: x["race_number"]):
                prob_pct = int(g["top1_prob"] * 100)
                race_parts.append(f"{g['race_number']}R({prob_pct}%)")
            parts.append(f"<p><strong>{venue}</strong>: {', '.join(race_parts)}</p>")

    # Footer
    parts.append(ABOUT_SUIRI_AI)
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)

    # Collect venue names for hashtags
    venue_names = []
    for g in grades:
        name = STADIUMS.get(g["stadium_number"], "")
        if name and name not in venue_names:
            venue_names.append(name)
    hashtags = _build_hashtags(venue_names=venue_names[:3])

    return title, html_body, hashtags
