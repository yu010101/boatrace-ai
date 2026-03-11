"""Generate note.com articles from race predictions.

note.com's ProseMirror editor supports: <h2>, <h3>, <p>, <strong>, <ul><li>, <hr>.
It does NOT support: <h1>, <table>, <blockquote>, <code>.
We generate note.com-compatible HTML directly (no Markdown→HTML conversion).
"""

from __future__ import annotations

from collections import defaultdict

from boatrace_ai import config
from boatrace_ai.data.constants import RACER_CLASSES, STADIUMS
from boatrace_ai.data.models import PredictionResult, RaceProgram

AccuracyRecord = dict  # type alias for readability

DISCLAIMER = (
    "この予測はAI（機械学習モデル）による統計分析に基づくものです。"
    "的中を保証するものではありません。舟券の購入は自己責任でお願いします。"
)

ABOUT_SUIRI_AI = (
    "<h3>水理AIとは</h3>"
    "<p>ボートレース全場・全レースを毎朝自動分析するAI予測サービスです。"
    "LightGBMと独自の特徴量エンジニアリングにより、選手・モーター・コース・展示データを"
    "総合的にスコアリング。毎日自動で予測→結果→検証のサイクルを回し、"
    "的中率・ROIの全履歴を改ざんなく公開しています。"
    "予測だけでなく「結果が正しかったか」まで毎日証明するAI予想です。</p>"
)


def _venue_names_from_grades(grades: list[dict]) -> list[str]:
    """Extract unique venue names from grade dicts."""
    names = []
    for g in grades:
        name = STADIUMS.get(g["stadium_number"], "")
        if name and name not in names:
            names.append(name)
    return names


def _venue_names_from_records(records: list[AccuracyRecord]) -> list[str]:
    """Extract unique venue names from accuracy records."""
    names = []
    for r in records:
        name = STADIUMS.get(r["stadium_number"], "")
        if name and name not in names:
            names.append(name)
    return names


def _format_venue_list(names: list[str], max_show: int = 3) -> str:
    """Format venue names for title: '桐生・戸田・江戸川など'."""
    if not names:
        return ""
    shown = names[:max_show]
    suffix = "など" if len(names) > max_show else ""
    return "・".join(shown) + suffix


def _format_date_short(race_date: str) -> str:
    """Convert '2026-03-06' to '3/6'."""
    parts = race_date.split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}/{int(parts[2])}"
    return race_date


def _build_track_record(stats: dict) -> str:
    """Build cumulative track record HTML for all articles."""
    total = stats.get("total_races", 0)
    if total == 0:
        return ""
    hit_1st_pct = round(stats["hit_1st_rate"] * 100)
    hit_tri_pct = round(stats["hit_trifecta_rate"] * 100)
    return (
        "<h3>累計実績</h3>"
        f"<p><strong>総予測: {total:,}レース | "
        f"1着的中率: {hit_1st_pct}% | "
        f"3連単的中率: {hit_tri_pct}%</strong></p>"
    )


_HASHTAGS_BY_TYPE: dict[str, list[str]] = {
    "prediction": ["競艇予想", "ボートレース予想", "AI予測", "競艇AI", "競艇", "無料予想", "AI競艇予想", "水理AI"],
    "results": ["競艇結果", "ボートレース結果", "的中", "AI予測", "競艇AI", "回収率", "AI競艇予想", "水理AI"],
    "track_record": ["競艇実績", "AI予測", "競艇AI", "回収率推移", "的中率", "AI競艇予想", "水理AI"],
    "midday": ["競艇速報", "午前結果", "ボートレース", "AI予測", "競艇AI", "AI競艇予想", "水理AI"],
}


def _build_hashtags(
    race: RaceProgram | None = None,
    *,
    venue_names: list[str] | None = None,
    article_type: str | None = None,
) -> list[str]:
    """Generate hashtags for the article."""
    if article_type and article_type in _HASHTAGS_BY_TYPE:
        tags = list(_HASHTAGS_BY_TYPE[article_type])
    else:
        tags = ["競艇", "ボートレース", "ボートレース予想", "AI予測", "競艇AI", "競艇予想", "AI競艇予想", "水理AI"]
    if race:
        stadium = STADIUMS.get(race.race_stadium_number, "")
        if stadium and stadium not in tags:
            tags.append(stadium)
    if venue_names:
        for name in venue_names:
            if name and name not in tags:
                tags.append(name)
    return tags[:10]


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
    confidence_pct = round(prediction.confidence * 100)

    parts: list[str] = []

    # ── Free section ──
    grade_label = f"【推奨度{grade}】" if grade else ""
    parts.append(f"<h2>{grade_label}{stadium}競艇 第{race.race_number}R AI予測｜{race.race_date}</h2>")

    # Context line about this race
    grade_desc = {
        "S": "AIが高い確信度で予測したSランクレースです。",
        "A": "AIが有力と判断したAランクレースです。",
        "B": "Bランク（予測可能）のレースです。",
        "C": "予測難度が高いCランクのレースです。",
    }
    context_text = grade_desc.get(grade, "") if grade else ""
    if context_text:
        parts.append(f"<p>{stadium} 第{race.race_number}R。{context_text}</p>")

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
        parts.append(
            "<p>ここから先は、AIの詳細分析と全艇のデータをお届けします。</p>"
        )

        # ── Pay wall ──
        parts.append("<pay>")

    # ── Detail section (paid when not free, always included) ──
    parts.append("<h2>AI詳細分析</h2>")
    parts.append(f"<p>{prediction.analysis}</p>")

    # Race data — each boat as a formatted <p> line
    parts.append("<h2>出走表データ</h2>")
    parts.append("<p>各艇の選手成績・機力データを一覧で確認できます。</p>")
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
            f"{boat.racer_name}（{cls}）"
            f"</p>"
            f"<p>"
            f"全国勝率 {boat.racer_national_top_1_percent:.1f}%｜"
            f"当地勝率 {boat.racer_local_top_1_percent:.1f}%｜"
            f"平均ST {st}｜"
            f"モーター {boat.racer_assigned_motor_top_2_percent:.1f}%｜"
            f"ボート {boat.racer_assigned_boat_top_2_percent:.1f}%"
            f"</p>"
        )
    if not free:
        parts.append("<hr>")

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
    confidence_pct = round(prediction.confidence * 100)

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
    lines.append("ボートレース全場・全レースを毎朝自動分析するAI予測サービス。的中率・ROIは改ざんなく公開。")
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
        title = f"【推奨度{grade}】{stadium}競艇 {race.race_number}R 予想｜AI予測 {race.race_date}"
    else:
        title = f"{stadium}競艇 {race.race_number}R 予想｜AI予測 {race.race_date}"

    html_body = _build_html(race, prediction, free=free, grade=grade)
    hashtags = _build_hashtags(race, article_type="prediction")

    return title, html_body, hashtags


# ── Accuracy report ──────────────────────────────────────────


def _build_accuracy_html(
    race_date: str,
    records: list[AccuracyRecord],
    stats: dict,
    roi_stats: dict | None = None,
    related_links: dict[str, dict] | None = None,
) -> str:
    """Build note.com-compatible HTML for accuracy report."""
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_tri = sum(1 for r in records if r["hit_trifecta"])
    hit_1st_pct = round(hit_1st / total * 100) if total else 0
    hit_tri_pct = round(hit_tri / total * 100) if total else 0

    venue_names = _venue_names_from_records(records)
    num_venues = len(venue_names)

    parts: list[str] = []

    date_short = _format_date_short(race_date)

    # ── Summary (first sentence = meta description for SEO) ──
    parts.append("<h2>ボートレースAI予想 本日の結果</h2>")
    parts.append(
        f"<p>{date_short}は全{num_venues}場{total}レースを予測しました。"
        f"1着的中率{hit_1st_pct}%（{hit_1st}/{total}）、"
        f"3連単的中{hit_tri}本を記録しています。</p>"
    )
    parts.append(
        f"<p><strong>1着的中: {hit_1st}/{total} ({hit_1st_pct}%) | "
        f"3連単的中: {hit_tri}/{total} ({hit_tri_pct}%)</strong></p>"
    )

    # ROI for the day
    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = round(roi_stats["roi"] * 100)
        profit = roi_stats["profit"]
        profit_label = "プラス収支" if profit > 0 else "マイナス収支"
        parts.append(
            f"<p>本日ROI: <strong>{roi_pct}%</strong>"
            f"（投資 ¥{roi_stats['total_invested']:,}"
            f" → 払戻 ¥{roi_stats['total_payout']:,}"
            f" / 損益 ¥{profit:+,} {profit_label}）</p>"
        )

    # ── Highlight: trifecta hits ──
    tri_hits = [r for r in records if r["hit_trifecta"]]
    if tri_hits:
        total_payout = sum(r.get("trifecta_payout", 0) for r in tri_hits)
        payout_note = ""
        if total_payout > 0:
            payout_note = f" 合計払戻 <strong>¥{total_payout:,}</strong>（100円あたり）"
        parts.append("<h3>本日のハイライト — 3連単的中</h3>")
        parts.append(
            f"<p>本日は{len(tri_hits)}レースで3連単を的中。"
            f"AIが着順まで正確に読み切ったレースです。{payout_note}</p>"
        )
        for r in tri_hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            payout = r.get("trifecta_payout", 0)
            payout_str = f" <strong>¥{payout:,}</strong>" if payout > 0 else ""
            parts.append(
                f"<p><strong>{stadium} {r['race_number']}R — 3連単的中!</strong> "
                f"予測 {r['predicted_trifecta']} → 結果 {r['actual_trifecta']}{payout_str}</p>"
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

    # ── Cumulative track record ──
    track_record = _build_track_record(stats)
    if track_record:
        parts.append(track_record)

    # ── Tomorrow teaser ──
    parts.append("<h3>明日の予測について</h3>")
    parts.append(
        "<p>水理AIは毎朝7:30に全場の予測を無料公開中。"
        "フォローすると翌朝すぐにAI予測をチェックできます。"
        "予測→結果→検証を365日自動で回し続けるAI予想です。</p>"
    )

    # ── Upsell ──
    parts.append("<h3>Sランク詳細予測を毎日受け取るには</h3>")
    parts.append(
        "<p>全レースの1着予測は毎朝無料で公開しています。"
        "さらにSランクレースの詳細な買い目・AI分析が必要な方は、"
        "有料記事またはメンバーシップをご検討ください。</p>"
    )

    parts.append(_membership_upsell())

    # Related articles
    if related_links:
        related = _build_related_articles("results", related_links)
        if related:
            parts.append(related)

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
    hit_1st_pct = round(hit_1st / total * 100) if total else 0
    hit_tri_pct = round(hit_tri / total * 100) if total else 0

    lines: list[str] = []

    lines.append(f"## 本日の結果サマリー")
    lines.append("")
    lines.append(
        f"**1着的中: {hit_1st}/{total} ({hit_1st_pct}%) | "
        f"3連単的中: {hit_tri}/{total} ({hit_tri_pct}%)**"
    )
    lines.append("")

    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = round(roi_stats["roi"] * 100)
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
    lines.append("### 累計実績")
    lines.append("")
    cum_total = stats["total_races"]
    cum_1st_pct = round(stats["hit_1st_rate"] * 100)
    cum_tri_pct = round(stats["hit_trifecta_rate"] * 100)
    lines.append(
        f"総予測: {cum_total:,}レース | "
        f"1着的中率: {cum_1st_pct}% | "
        f"3連単的中率: {cum_tri_pct}%"
    )
    lines.append("")
    lines.append("### 水理AIとは")
    lines.append("ボートレース全場・全レースを毎朝自動分析するAI予測サービス。的中率・ROIは改ざんなく公開。")
    lines.append("")
    lines.append("### 注意事項")
    lines.append(DISCLAIMER)

    return "\n".join(lines)


def generate_accuracy_report(
    race_date: str,
    records: list[AccuracyRecord],
    stats: dict,
    roi_stats: dict | None = None,
    related_links: dict[str, dict] | None = None,
) -> tuple[str, str, list[str]]:
    """Generate a note.com accuracy report article.

    Args:
        race_date: The date of the races (YYYY-MM-DD)
        records: List of accuracy records from get_accuracy_for_date()
        stats: Cumulative stats from get_stats()
        roi_stats: Optional ROI stats for the date
        related_links: Optional related article links for cross-linking

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_1st_pct = round(hit_1st / total * 100) if total else 0

    venue_names = _venue_names_from_records(records)
    venue_str = _format_venue_list(venue_names)
    num_venues = len(venue_names)
    date_short = _format_date_short(race_date)

    title = (
        f"競艇AI予想 結果｜{venue_str}全{num_venues}場"
        f"【的中率{hit_1st_pct}%】{date_short}"
    )
    html_body = _build_accuracy_html(
        race_date, records, stats, roi_stats=roi_stats, related_links=related_links
    )

    hashtags = _build_hashtags(venue_names=venue_names[:3], article_type="results")

    return title, html_body, hashtags


# ── Grade summary article ────────────────────────────────────


def generate_grade_summary_article(
    race_date: str,
    grades: list[dict],
    stats: dict | None = None,
    predictions: dict[tuple[int, int], list[int]] | None = None,
    related_links: dict[str, dict] | None = None,
) -> tuple[str, str, list[str]]:
    """Generate a free article listing all race grades with 1st-place predictions.

    Args:
        race_date: The date (YYYY-MM-DD)
        grades: List of grade dicts from get_grades_for_date()
        stats: Optional cumulative stats from get_stats() for displaying hit rates
        predictions: Optional mapping of (stadium, race_number) -> predicted_order

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    s_count = sum(1 for g in grades if g["grade"] == "S")
    a_count = sum(1 for g in grades if g["grade"] == "A")
    venue_names = _venue_names_from_grades(grades)
    venue_str = _format_venue_list(venue_names)
    num_venues = len(venue_names)
    date_short = _format_date_short(race_date)

    # Build title: competitor-beating format with venue names and free marker
    if stats and stats.get("total_races", 0) > 0:
        hit_1st_pct = round(stats["hit_1st_rate"] * 100)
        title = (
            f"競艇AI予想｜{venue_str}全{num_venues}場"
            f"【全レース1着予測無料】的中率{hit_1st_pct}% {date_short}"
        )
    else:
        title = (
            f"競艇AI予想｜{venue_str}全{num_venues}場"
            f"【全レース1着予測無料】{date_short}"
        )

    parts: list[str] = []
    total_races = len(grades)

    # ── Opening (first sentence = meta description for SEO) ──
    parts.append("<h2>本日の競艇AI予想</h2>")

    # Dynamic opening based on what makes today interesting
    if s_count >= 5:
        opener = (
            f"<p>本日はSランク（高確信）が{s_count}レースと多め。"
            f"狙い目の多い一日です。"
        )
    elif s_count == 0:
        opener = (
            f"<p>本日はSランク該当なし。難解な番組が多い一日です。"
            f"Aランク{a_count}レースを中心に慎重に狙いたいところ。"
        )
    else:
        opener = (
            f"<p>本日は{venue_str}を含む全{num_venues}場{total_races}レースをAIが分析。"
            f"Sランク{s_count}レース、Aランク{a_count}レースを検出しました。"
        )
    opener += f"全レースの1着予測を無料で公開しています。"
    opener += f"毎朝7:30に全場を自動分析 — 予測→結果→検証を365日繰り返すAI予想です。</p>"
    parts.append(opener)

    if stats and stats.get("total_races", 0) > 0:
        hit_1st_pct = round(stats["hit_1st_rate"] * 100)
        hit_tri_pct = round(stats["hit_trifecta_rate"] * 100)
        parts.append(
            f"<p><strong>直近の実績: 1着的中率 {hit_1st_pct}% / "
            f"3連単的中率 {hit_tri_pct}%</strong></p>"
        )

    # ── 本日のポイント ──
    parts.append("<h3>本日のポイント</h3>")
    point_items: list[str] = []
    if s_count > 0:
        point_items.append(
            f"<li>Sランク（高確信）{s_count}レース — 最も期待値の高い予測です</li>"
        )
    if a_count > 0:
        point_items.append(
            f"<li>Aランク（有力）{a_count}レース — 堅実に狙えるレースです</li>"
        )
    point_items.append(
        f"<li>全{total_races}レースの1着予測をこの記事で無料公開中</li>"
    )
    parts.append(f"<ul>{''.join(point_items)}</ul>")

    # ── TOP3 注目レース ──
    s_races = sorted(
        [g for g in grades if g["grade"] == "S"],
        key=lambda g: g["top1_prob"],
        reverse=True,
    )
    if s_races:
        top3 = s_races[:3]
        parts.append("<h3>注目レース TOP3</h3>")
        parts.append(
            "<p>本日、AIが最も高い確信度を示したレースです。"
            "Sランクの中でもとくに数値が突出しています。</p>"
        )
        for g in top3:
            stadium = STADIUMS.get(g["stadium_number"], str(g["stadium_number"]))
            prob_pct = round(g["top1_prob"] * 100)
            # Include predicted 1st boat if available
            pred_text = ""
            if predictions:
                order = predictions.get((g["stadium_number"], g["race_number"]))
                if order:
                    pred_text = f" ◎{order[0]}号艇"
            parts.append(
                f"<p><strong>{stadium} {g['race_number']}R{pred_text}</strong>: "
                f"本命確率 {prob_pct}%（Sランク）</p>"
            )

    # ── All races with 1st-place predictions grouped by venue ──
    rank_descriptions = {
        "S": "AIの確信度が高く、最も期待値の高いレースです。",
        "A": "Sランクに次ぐ有力レース。堅実な予測が見込めます。",
        "B": "標準的な予測精度のレース。参考情報としてご活用ください。",
        "C": "予測の難度が高いレースです。見送りも選択肢のひとつ。",
    }

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
        parts.append(f"<p>{rank_descriptions[rank]}</p>")

        # Group by venue for readability
        by_venue: dict[str, list] = defaultdict(list)
        for g in rank_grades:
            venue = STADIUMS.get(g["stadium_number"], str(g["stadium_number"]))
            by_venue[venue].append(g)

        for venue, venue_grades in sorted(by_venue.items()):
            race_parts = []
            for g in sorted(venue_grades, key=lambda x: x["race_number"]):
                prob_pct = round(g["top1_prob"] * 100)
                # Show ◎○△ predictions if available
                if predictions:
                    order = predictions.get((g["stadium_number"], g["race_number"]))
                    if order and len(order) >= 3:
                        race_parts.append(
                            f"{g['race_number']}R ◎{order[0]} ○{order[1]} △{order[2]}({prob_pct}%)"
                        )
                    else:
                        race_parts.append(f"{g['race_number']}R({prob_pct}%)")
                else:
                    race_parts.append(f"{g['race_number']}R({prob_pct}%)")
            parts.append(f"<p><strong>{venue}</strong>: {', '.join(race_parts)}</p>")

    # ── Upsell to paid articles ──
    if s_count > 0:
        parts.append("<hr>")
        parts.append("<h3>Sランクの詳細予測を見るには</h3>")
        parts.append(
            f"<p>この記事では全レースの1着予測を公開していますが、"
            f"Sランク{s_count}レースの<strong>詳細な買い目・3連単予測・AI分析</strong>"
            f"は個別の有料記事で配信しています。"
            f"水理AIのプロフィールから最新記事をご確認ください。</p>"
        )

    # ── Track record ──
    if stats:
        track_record = _build_track_record(stats)
        if track_record:
            parts.append(track_record)

    parts.append(_membership_upsell())

    # Related articles
    if related_links:
        related = _build_related_articles("grades", related_links)
        if related:
            parts.append(related)

    # Footer
    parts.append(ABOUT_SUIRI_AI)
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)

    hashtags = _build_hashtags(venue_names=venue_names[:3], article_type="prediction")

    return title, html_body, hashtags


# ── Related articles ──────────────────────────────────────────


def _build_related_articles(current_type: str, links: dict[str, dict]) -> str:
    """Build related articles section. note.com auto-links URLs."""
    type_labels = {
        "grades": "本日の全レース予測",
        "results": "昨日の結果レポート",
        "track_record": "過去30日の実績推移",
        "midday": "午前の中間速報",
        "membership": "メンバーシップのご案内",
    }
    items = []
    for article_type, article in links.items():
        if article_type == current_type:
            continue
        label = type_labels.get(article_type, article_type)
        items.append(f"<p>{label} → {article['note_url']}</p>")
    if not items:
        return ""
    return "<h3>関連記事</h3>\n" + "\n".join(items)


# ── Membership upsell ─────────────────────────────────────────


def _membership_upsell() -> str:
    """Build membership upsell HTML with config-driven price."""
    price = config.NOTE_MEMBERSHIP_PRICE
    article_price = config.NOTE_ARTICLE_PRICE
    daily = round(price / 30)
    return (
        "<h3>メンバーシップのご案内</h3>"
        f"<p>Sランク詳細予測は通常¥{article_price:,}/記事。"
        f"メンバーシップなら毎朝のSランク記事がすべて読み放題で"
        f"<strong>月額¥{price:,}</strong>（1日約¥{daily}）。"
        f"1記事分の料金で1ヶ月分の予測を受け取れます。</p>"
        f"<p>3連単的中時は1万円超の払戻も。"
        f"毎朝の予測に加え、結果レポートで回収率まで毎日検証。"
        f"詳しくは水理AIのプロフィールから。</p>"
    )


# Keep backward-compatible constant for existing imports
MEMBERSHIP_UPSELL = _membership_upsell()


# ── Track record article (weekly) ────────────────────────────


def generate_track_record_article(
    accuracy_trend: list[dict],
    roi_trend: list[dict],
    stats: dict,
    related_links: dict[str, dict] | None = None,
) -> tuple[str, str, list[str]]:
    """Generate weekly track record article with accuracy/ROI trends.

    Args:
        accuracy_trend: From get_accuracy_trend(30)
        roi_trend: From get_roi_trend(30)
        stats: From get_stats()
        related_links: Optional dict of article_type -> {note_url, title}
    """
    total = stats.get("total_races", 0)
    hit_1st_pct = round(stats["hit_1st_rate"] * 100) if total > 0 else 0
    roi_pct = 0
    if roi_trend:
        total_invested = sum(r["invested"] for r in roi_trend)
        total_payout = sum(r["payout"] for r in roi_trend)
        roi_pct = round(total_payout / total_invested * 100) if total_invested > 0 else 0

    title = f"競艇AI実績｜直近30日の的中率・ROI推移【全データ公開】"

    parts: list[str] = []

    # First sentence = OGP/meta description
    parts.append("<h2>水理AI 過去30日間の予測実績</h2>")
    parts.append(
        f"<p>ボートレースAI予想「水理AI」の直近30日間の的中率・回収率を全データ公開。"
        f"1着的中率{hit_1st_pct}%、回収率{roi_pct}%の推移です。</p>"
    )

    # Summary
    parts.append("<h3>サマリー</h3>")
    total_races_30d = sum(r["total"] for r in accuracy_trend)
    hit_1st_30d = sum(r["hit_1st"] for r in accuracy_trend)
    hit_tri_30d = sum(r["hit_tri"] for r in accuracy_trend)
    rate_1st = round(hit_1st_30d / total_races_30d * 100) if total_races_30d > 0 else 0
    rate_tri = round(hit_tri_30d / total_races_30d * 100) if total_races_30d > 0 else 0
    parts.append(
        f"<p><strong>総予測: {total_races_30d}レース | "
        f"1着的中率: {rate_1st}% | 3連単的中率: {rate_tri}% | ROI: {roi_pct}%</strong></p>"
    )

    # Daily breakdown (last 7 days)
    parts.append("<h3>日別実績（直近7日）</h3>")
    for acc in accuracy_trend[:7]:
        d = acc["date"]
        date_short = _format_date_short(d)
        pct = round(acc["hit_1st_rate"] * 100)
        # Find matching ROI
        roi_day = next((r for r in roi_trend if r["date"] == d), None)
        roi_label = f" / ROI {round(roi_day['roi'] * 100)}%" if roi_day else ""
        parts.append(
            f"<p><strong>{date_short}</strong>: "
            f"{acc['total']}R → 1着{acc['hit_1st']}的中({pct}%){roi_label}</p>"
        )

    # Trend analysis
    if len(accuracy_trend) >= 14:
        recent_7 = accuracy_trend[:7]
        prev_7 = accuracy_trend[7:14]
        recent_total = sum(r["total"] for r in recent_7)
        prev_total = sum(r["total"] for r in prev_7)
        recent_rate = sum(r["hit_1st"] for r in recent_7) / recent_total * 100 if recent_total else 0
        prev_rate = sum(r["hit_1st"] for r in prev_7) / prev_total * 100 if prev_total else 0
        diff = recent_rate - prev_rate
        direction = "改善" if diff >= 0 else "低下"
        parts.append("<h3>トレンド分析</h3>")
        parts.append(
            f"<p>前7日 → 直近7日: 1着的中率 {round(prev_rate)}% → {round(recent_rate)}%"
            f"（{diff:+.0f}pt {direction}）</p>"
        )

    # Membership upsell
    parts.append(_membership_upsell())

    # Related articles
    if related_links:
        related = _build_related_articles("track_record", related_links)
        if related:
            parts.append(related)

    parts.append(ABOUT_SUIRI_AI)
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)
    hashtags = _build_hashtags(article_type="track_record")

    return title, html_body, hashtags


# ── Midday report ─────────────────────────────────────────────


def generate_midday_report(
    race_date: str,
    records: list[AccuracyRecord],
    related_links: dict[str, dict] | None = None,
) -> tuple[str, str, list[str]]:
    """Generate midday (morning session) results report.

    Args:
        race_date: The date (YYYY-MM-DD)
        records: Accuracy records available so far (morning races)
        related_links: Optional related article links
    """
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_tri = sum(1 for r in records if r["hit_trifecta"])
    hit_1st_pct = round(hit_1st / total * 100) if total else 0

    venue_names = _venue_names_from_records(records)
    venue_str = _format_venue_list(venue_names)
    date_short = _format_date_short(race_date)

    title = (
        f"競艇AI予想 午前の結果速報｜{venue_str}"
        f"【的中率{hit_1st_pct}%】{date_short}"
    )

    parts: list[str] = []

    hit_tri_pct = round(hit_tri / total * 100) if total else 0

    # First sentence = OGP — urgent 速報 tone
    parts.append("<h2>午前の部 結果速報</h2>")
    parts.append(
        f"<p>{date_short} 午前{total}レースの中間結果が出ました。</p>"
    )
    parts.append(
        f"<p><strong>1着的中: {hit_1st}/{total}（{hit_1st_pct}%）| "
        f"3連単的中: {hit_tri}/{total}（{hit_tri_pct}%）</strong></p>"
    )

    # Highlights
    tri_hits = [r for r in records if r["hit_trifecta"]]
    if tri_hits:
        parts.append("<h3>午前のハイライト</h3>")
        for r in tri_hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            parts.append(
                f"<p><strong>{stadium} {r['race_number']}R — 3連単的中!</strong> "
                f"予測: {r['predicted_trifecta']} → 結果: {r['actual_trifecta']}</p>"
            )

    # Afternoon pointer
    parts.append("<hr>")
    parts.append("<h3>午後のレースについて</h3>")
    parts.append(
        "<p>午後もSランクレースを中心に予測を配信中です。"
        "最新の予測記事はプロフィールからご確認ください。"
        "最終結果は夜の結果レポートでまとめてお届けします。</p>"
    )

    # Related articles
    if related_links:
        related = _build_related_articles("midday", related_links)
        if related:
            parts.append(related)

    parts.append(ABOUT_SUIRI_AI)
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)
    hashtags = _build_hashtags(venue_names=venue_names[:3], article_type="midday")

    return title, html_body, hashtags


# ── Membership article ────────────────────────────────────────


def generate_membership_article(
    stats: dict,
    related_links: dict[str, dict] | None = None,
) -> tuple[str, str, list[str]]:
    """Generate membership introduction article.

    Args:
        stats: Cumulative stats from get_stats()
        related_links: Optional related article links
    """
    title = "水理AI メンバーシップ｜毎日のSランク詳細予測を月額でお得に"

    parts: list[str] = []

    parts.append("<h2>水理AIメンバーシップのご案内</h2>")
    parts.append(
        "<p>ボートレースAI予想「水理AI」の毎朝のSランク詳細予測・買い目を月額制でお届けします。</p>"
    )

    parts.append("<h3>メンバー特典</h3>")
    parts.append(
        "<ul>"
        f"<li>毎朝Sランク全レースの詳細買い目（通常¥{config.NOTE_ARTICLE_PRICE}/記事）</li>"
        "<li>週次実績レポート</li>"
        "<li>優先お知らせ配信</li>"
        "</ul>"
    )

    parts.append("<h3>料金</h3>")
    parts.append(
        f"<p><strong>月額¥{config.NOTE_MEMBERSHIP_PRICE:,}</strong>（1日約¥{round(config.NOTE_MEMBERSHIP_PRICE / 30)}）</p>"
    )

    # Track record
    track_record = _build_track_record(stats)
    if track_record:
        parts.append(track_record)

    # Related articles
    if related_links:
        related = _build_related_articles("membership", related_links)
        if related:
            parts.append(related)

    parts.append(ABOUT_SUIRI_AI)
    parts.append("<h3>注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)
    hashtags = _build_hashtags(article_type="prediction")

    return title, html_body, hashtags
