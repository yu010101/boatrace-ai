"""Generate note.com articles from race predictions.

note.com's ProseMirror editor supports: <h2>, <h3>, <p>, <strong>, <ul><li>, <hr>.
It does NOT support: <h1>, <table>, <blockquote>, <code>.
We generate note.com-compatible HTML directly (no Markdown→HTML conversion).
"""

from __future__ import annotations

from collections import defaultdict

from boatrace_ai import config
from boatrace_ai.data.constants import RACER_CLASSES, STADIUMS, TECHNIQUES
from boatrace_ai.data.models import PredictionResult, RaceProgram

AccuracyRecord = dict  # type alias for readability

DISCLAIMER = (
    "この予測はAI（機械学習モデル）による統計分析に基づくものです。"
    "的中を保証するものではありません。舟券の購入は自己責任でお願いします。"
)

_ABOUT_SUIRI_AI_STATIC = (
    "<h3>◆ 水理AIとは</h3>"
    "<p>ボートレース全場・全レースを毎朝自動分析するAI予測サービスです。"
    "LightGBMと独自の特徴量エンジニアリングにより、選手・モーター・コース・展示データを"
    "総合的にスコアリング。</p>"
    "<ul>"
    "<li>全履歴公開 … <strong>勝ちも負けも改ざんなく公開</strong></li>"
    "<li>完全自動 … <strong>予測→結果→検証を365日毎日</strong></li>"
    "</ul>"
    "<p>予測だけでなく「結果が正しかったか」まで毎日証明するAI予想です。</p>"
)

# Backward-compatible alias
ABOUT_SUIRI_AI = _ABOUT_SUIRI_AI_STATIC


def _build_about_section(stats: dict | None = None) -> str:
    """Build dynamic 'About Suiri AI' section with live stats."""
    parts = [
        "<h3>◆ 水理AIとは</h3>",
        "<p>ボートレース全場・全レースを毎朝自動分析するAI予測サービスです。"
        "LightGBMと独自の特徴量エンジニアリングにより、選手・モーター・コース・展示データを"
        "総合的にスコアリング。</p>",
    ]
    items = []
    if stats and stats.get("total_races", 0) > 0:
        items.append(
            f"<li>累計分析 … <strong>{stats['total_races']:,}レース以上</strong></li>"
        )
    try:
        from boatrace_ai.storage.database import get_operation_days
        days = get_operation_days()
        if days > 0:
            items.append(
                f"<li>連続運用 … <strong>{days}日目</strong>（毎日自動運用）</li>"
            )
    except Exception:
        pass
    items.append(
        "<li>全履歴公開 … <strong>勝ちも負けも改ざんなく公開</strong></li>"
    )
    if items:
        parts.append(f"<ul>{''.join(items)}</ul>")
    parts.append(
        "<p>予測だけでなく「結果が正しかったか」まで毎日証明するAI予想です。</p>"
    )
    return "\n".join(parts)


def _build_opening_hook(
    hit_1st_pct: int,
    hit_tri: int,
    total: int,
    max_payout: int = 0,
    roi_pct: int = 0,
) -> str:
    """Generate emotional opening line based on today's results."""
    if max_payout >= 10000:
        return "万舟的中！ 大穴を捉えたAIの分析力が際立つ一日でした。"
    if hit_tri >= 5 and roi_pct >= 100:
        return f"3連単{hit_tri}本的中、ROI {roi_pct}%。攻守ともに好調な一日でした。"
    if hit_tri >= 5:
        return (
            f"3連単{hit_tri}本的中！ 回収率は課題が残りますが、的中力は健在です。"
        )
    if hit_1st_pct >= 50:
        return f"1着的中率{hit_1st_pct}%と安定した一日。堅い予測が光りました。"
    if hit_1st_pct < 40:
        return (
            "本日は苦戦。波乱含みの展開にAIも対応しきれませんでした。"
            "率直に振り返ります。"
        )
    return "本日の予測結果をまとめました。良かった点・課題の両面をレポートします。"


def _build_loss_analysis(
    records: list[AccuracyRecord],
    results_data: list[dict] | None,
) -> str:
    """Analyze loss patterns when overall results are weak."""
    total = len(records)
    if total == 0:
        return ""
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_1st_pct = round(hit_1st / total * 100)
    if hit_1st_pct >= 45:
        return ""  # Not a bad day, skip

    parts: list[str] = []
    parts.append("<h3>◆ 今日の敗因分析</h3>")

    items: list[str] = []

    # Find worst venue
    venue_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "hit": 0})
    for r in records:
        venue = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
        venue_stats[venue]["total"] += 1
        if r["hit_1st"]:
            venue_stats[venue]["hit"] += 1

    if venue_stats:
        worst = min(
            venue_stats.items(),
            key=lambda x: x[1]["hit"] / x[1]["total"] if x[1]["total"] > 0 else 0,
        )
        worst_pct = round(worst[1]["hit"] / worst[1]["total"] * 100) if worst[1]["total"] else 0
        items.append(
            f"<li><strong>最も苦戦した場</strong>　"
            f"{worst[0]} — 的中率{worst_pct}%（{worst[1]['hit']}/{worst[1]['total']}）</li>"
        )

    # Inner course analysis from results_data
    if results_data:
        inner_wins = sum(1 for r in results_data if r.get("actual_1st") == 1)
        total_results = len(results_data)
        if total_results > 0:
            inner_pct = round(inner_wins / total_results * 100)
            if inner_pct < 45:
                items.append(
                    f"<li><strong>1号艇1着率が低調</strong>　{inner_pct}%"
                    f"（平均約55%）— 波乱傾向の日でした</li>"
                )

    # Miss streak
    miss_count = sum(1 for r in records if not r["hit_1st"])
    items.append(
        f"<li><strong>予測外し</strong>　{miss_count}/{total}レース"
        f"（{round(miss_count / total * 100)}%）</li>"
    )

    items.append(
        "<li>AIは毎日の結果を学習データとして蓄積。"
        "苦戦した日のパターンも次回以降の改善に活かされます。</li>"
    )

    if items:
        parts.append(f"<ul>{''.join(items)}</ul>")

    return "\n".join(parts)


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
    """Build cumulative track record HTML as pseudo-table."""
    total = stats.get("total_races", 0)
    if total == 0:
        return ""
    hit_1st_pct = round(stats["hit_1st_rate"] * 100)
    hit_tri_pct = round(stats["hit_trifecta_rate"] * 100)
    items = [
        f"<li>総予測レース … <strong>{total:,}レース</strong></li>",
        f"<li>1着的中率 …… <strong>{hit_1st_pct}%</strong></li>",
        f"<li>3連単的中率 … <strong>{hit_tri_pct}%</strong></li>",
    ]
    return f"<h3>◆ 累計実績</h3>\n<ul>{''.join(items)}</ul>"


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


def _build_hit_analysis(
    record: AccuracyRecord,
    prediction: dict | None,
    result: dict | None,
) -> str:
    """Build 2-4 sentence analysis of why a trifecta hit occurred."""
    sentences: list[str] = []

    # Confidence
    if prediction and prediction.get("confidence"):
        conf_pct = round(prediction["confidence"] * 100)
        sentences.append(f"AIの信頼度は{conf_pct}%")

    # Technique (決まり手)
    tech_num = result.get("technique_number") if result else None
    if tech_num and tech_num in TECHNIQUES:
        sentences.append(f"決まり手は「{TECHNIQUES[tech_num]}」")

    # Analysis excerpt (first sentence from prediction analysis)
    if prediction and prediction.get("analysis"):
        analysis = prediction["analysis"]
        # Take first sentence (up to 。or 60 chars)
        first = analysis.split("。")[0]
        if len(first) > 60:
            first = first[:57] + "..."
        if first:
            sentences.append(first)

    # Payout
    payout = record.get("trifecta_payout", 0)
    if payout >= 10000:
        sentences.append(f"払戻¥{payout:,}の万舟")
    elif payout > 0:
        sentences.append(f"払戻¥{payout:,}")

    if not sentences:
        return ""
    return "（" + "。".join(sentences) + "）"


def _build_daily_trends(
    records: list[AccuracyRecord],
    results_data: list[dict],
) -> str:
    """Build daily trends section: venue analysis, technique distribution, inner course rate."""
    if not results_data:
        return ""

    parts: list[str] = []
    parts.append("<h2>━━ 本日の傾向分析 ━━</h2>")

    trend_items: list[str] = []

    # ── Technique distribution ──
    tech_counts: dict[str, int] = defaultdict(int)
    for r in results_data:
        tech = r.get("technique_number")
        if tech and tech in TECHNIQUES:
            tech_counts[TECHNIQUES[tech]] += 1
    if tech_counts:
        total_with_tech = sum(tech_counts.values())
        tech_parts = []
        for name, count in sorted(tech_counts.items(), key=lambda x: -x[1]):
            pct = round(count / total_with_tech * 100)
            tech_parts.append(f"{name} {count}本（{pct}%）")
        trend_items.append(
            f"<li><strong>決まり手</strong>　{'／'.join(tech_parts)}</li>"
        )

    # ── Inner course (1号艇) win rate ──
    inner_wins = sum(1 for r in results_data if r.get("actual_1st") == 1)
    total_races = len(results_data)
    if total_races > 0:
        inner_pct = round(inner_wins / total_races * 100)
        if inner_pct > 55:
            avg_label = "▲ 高め（堅い日）"
        elif inner_pct < 45:
            avg_label = "▼ 低め（荒れた日）"
        else:
            avg_label = "― 平均並み"
        trend_items.append(
            f"<li><strong>1号艇1着率</strong>　{inner_pct}%"
            f"（{inner_wins}/{total_races}）{avg_label}</li>"
        )

    # ── Best/worst venue ──
    venue_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "hit": 0})
    for r in records:
        venue = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
        venue_stats[venue]["total"] += 1
        if r["hit_1st"]:
            venue_stats[venue]["hit"] += 1

    if len(venue_stats) >= 3:
        ranked = sorted(
            venue_stats.items(),
            key=lambda x: x[1]["hit"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=True,
        )
        best = ranked[0]
        worst = ranked[-1]
        best_pct = round(best[1]["hit"] / best[1]["total"] * 100) if best[1]["total"] else 0
        worst_pct = round(worst[1]["hit"] / worst[1]["total"] * 100) if worst[1]["total"] else 0
        trend_items.append(
            f"<li><strong>AI好調場</strong>　{best[0]} {best_pct}%"
            f"（{best[1]['hit']}/{best[1]['total']}）</li>"
        )
        trend_items.append(
            f"<li><strong>AI苦戦場</strong>　{worst[0]} {worst_pct}%"
            f"（{worst[1]['hit']}/{worst[1]['total']}）</li>"
        )

    if trend_items:
        parts.append(f"<ul>{''.join(trend_items)}</ul>")

    return "\n".join(parts) if len(parts) > 1 else ""


def _build_trend_text(
    accuracy_trend: list[dict],
    roi_trend: list[dict],
) -> str:
    """Build text-based 7-day trend display using note.com-safe HTML."""
    if not accuracy_trend:
        return ""
    days = list(reversed(accuracy_trend[:7]))
    roi_map = {r["date"]: r for r in roi_trend} if roi_trend else {}

    parts: list[str] = []
    parts.append("<h3>◆ 直近7日間の推移</h3>")

    items: list[str] = []
    for acc in days:
        d = acc["date"]
        date_label = _format_date_short(d)
        hit_pct = round(acc["hit_1st_rate"] * 100)
        tri_count = acc.get("hit_tri", 0)
        roi_day = roi_map.get(d)

        # Visual bar
        bar_len = max(1, hit_pct // 5)
        bar = "■" * bar_len + "□" * (20 - bar_len)

        roi_str = f"｜ROI {round(roi_day['roi'] * 100)}%" if roi_day else ""
        items.append(
            f"<li><strong>{date_label}</strong>　{bar}　{hit_pct}%"
            f"（3連単 {tri_count}本{roi_str}）</li>"
        )
    parts.append(f"<ul>{''.join(items)}</ul>")

    return "\n".join(parts)


def _build_accuracy_html(
    race_date: str,
    records: list[AccuracyRecord],
    stats: dict,
    roi_stats: dict | None = None,
    related_links: dict[str, dict] | None = None,
    chart_url: str | None = None,
    hit_analyses: dict[tuple[int, int], str] | None = None,
    results_data: list[dict] | None = None,
    accuracy_trend: list[dict] | None = None,
    roi_trend: list[dict] | None = None,
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

    # ━━━━ サマリー（SEOメタ + 数値一覧） ━━━━
    parts.append("<h2>ボートレースAI予想 本日の結果</h2>")

    # A1: Emotional opening hook
    max_payout = max((r.get("trifecta_payout", 0) for r in records), default=0)
    _roi_pct_for_hook = 0
    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        _roi_pct_for_hook = round(roi_stats["roi"] * 100)
    hook = _build_opening_hook(hit_1st_pct, hit_tri, total, max_payout, _roi_pct_for_hook)
    parts.append(f"<p><strong>{hook}</strong></p>")

    parts.append(
        f"<p>{date_short}は全{num_venues}場・{total}レースを予測。"
        f"1着的中率 <strong>{hit_1st_pct}%</strong>、"
        f"3連単的中 <strong>{hit_tri}本</strong> を記録しました。</p>"
    )

    # Summary card as structured list
    summary_items = [
        f"<li>1着的中 … <strong>{hit_1st}/{total}（{hit_1st_pct}%）</strong></li>",
        f"<li>3連単的中 … <strong>{hit_tri}/{total}（{hit_tri_pct}%）</strong></li>",
    ]
    if roi_stats and roi_stats.get("total_bets", 0) > 0:
        roi_pct = round(roi_stats["roi"] * 100)
        profit = roi_stats["profit"]
        profit_mark = "+" if profit > 0 else ""
        summary_items.append(
            f"<li>ROI … <strong>{roi_pct}%</strong>"
            f"（¥{roi_stats['total_invested']:,} → ¥{roi_stats['total_payout']:,}"
            f"｜損益 {profit_mark}¥{profit:,}）</li>"
        )
    parts.append(f"<ul>{''.join(summary_items)}</ul>")

    parts.append("<hr>")

    # ━━━━ 推移（チャート or テキスト） ━━━━
    if chart_url:
        parts.append(f'<p><img src="{chart_url}" alt="直近30日の的中率・ROI推移"></p>')
    elif accuracy_trend:
        trend_text = _build_trend_text(accuracy_trend, roi_trend or [])
        if trend_text:
            parts.append(trend_text)
            parts.append("<hr>")

    # ━━━━ ハイライト: 3連単的中 ━━━━
    tri_hits = [r for r in records if r["hit_trifecta"]]
    if tri_hits:
        total_payout = sum(r.get("trifecta_payout", 0) for r in tri_hits)
        payout_note = ""
        if total_payout > 0:
            payout_note = f"（合計払戻 <strong>¥{total_payout:,}</strong>）"
        parts.append("<h2>━━ 3連単的中ハイライト ━━</h2>")
        parts.append(
            f"<p>{len(tri_hits)}レースで3連単を的中。"
            f"AIが着順まで正確に読み切りました。{payout_note}</p>"
        )

        sorted_hits = sorted(tri_hits, key=lambda x: x.get("trifecta_payout", 0), reverse=True)
        hit_items: list[str] = []
        for r in sorted_hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            payout = r.get("trifecta_payout", 0)
            payout_str = f"　→ 払戻 <strong>¥{payout:,}</strong>" if payout > 0 else ""
            # Analysis
            analysis_str = ""
            if hit_analyses:
                key = (r["stadium_number"], r["race_number"])
                analysis_str = hit_analyses.get(key, "")

            hit_items.append(
                f"<li><strong>◎ {stadium} {r['race_number']}R</strong>"
                f"　予測 {r['predicted_trifecta']} → 結果 {r['actual_trifecta']}"
                f"{payout_str}</li>"
            )
            # Add analysis as separate paragraph after the list item
            if analysis_str:
                # Close current list, add analysis, reopen list
                hit_items.append(f"</ul><p>　　↳ {analysis_str}</p><ul>")

        parts.append(f"<ul>{''.join(hit_items)}</ul>")
        parts.append("<hr>")

    # ━━━━ 的中レース一覧（場別） ━━━━
    all_hits = [r for r in records if r["hit_1st"] or r["hit_trifecta"]]
    if all_hits:
        parts.append("<h3>◆ 的中レース一覧（場別）</h3>")
        by_venue: dict[str, list] = defaultdict(list)
        for r in all_hits:
            venue = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            by_venue[venue].append(r)

        venue_items: list[str] = []
        for venue, venue_records in sorted(by_venue.items()):
            race_parts = []
            for r in sorted(venue_records, key=lambda x: x["race_number"]):
                if r["hit_trifecta"]:
                    race_parts.append(f"<strong>{r['race_number']}R(3連単)</strong>")
                else:
                    race_parts.append(f"{r['race_number']}R(1着)")
            venue_items.append(f"<li><strong>{venue}</strong>　{' / '.join(race_parts)}</li>")
        parts.append(f"<ul>{''.join(venue_items)}</ul>")

    # ━━━━ 傾向分析 ━━━━
    if results_data:
        trends = _build_daily_trends(records, results_data)
        if trends:
            parts.append("<hr>")
            parts.append(trends)

    # ━━━━ A3: 敗因分析（苦戦日のみ表示） ━━━━
    loss = _build_loss_analysis(records, results_data)
    if loss:
        parts.append("<hr>")
        parts.append(loss)

    # ━━━━ 累計実績 ━━━━
    track_record = _build_track_record(stats)
    if track_record:
        parts.append("<hr>")
        parts.append(track_record)

    # ━━━━ C2: 明日の予測CTA ━━━━
    parts.append("<hr>")
    parts.append("<h3>◆ 明日の予測について</h3>")
    parts.append(
        "<p><strong>明日も朝7:30に全場のAI予測を無料公開します。</strong></p>"
    )
    parts.append(
        "<p>フォローしておくと、朝イチでSランクレースをチェックできます。"
        "予測→結果→検証を<strong>365日毎日</strong>自動で回し続けるAI予想です。</p>"
    )

    # ━━━━ Sランク誘導 ━━━━
    parts.append("<h3>◆ Sランク詳細予測を毎日受け取るには</h3>")
    parts.append(
        "<ul>"
        "<li>全レースの1着予測 … <strong>毎朝無料</strong>で公開中</li>"
        "<li>Sランクの詳細買い目・AI分析 … <strong>有料記事</strong>で配信</li>"
        "<li>月額メンバーシップで読み放題</li>"
        "</ul>"
    )
    parts.append(_membership_upsell())

    # Related articles
    if related_links:
        related = _build_related_articles("results", related_links)
        if related:
            parts.append(related)

    # E1: Dynamic about section with stats
    parts.append(_build_about_section(stats))
    parts.append("<h3>◆ 注意事項</h3>")
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
    chart_url: str | None = None,
    hit_analyses: dict[tuple[int, int], str] | None = None,
    results_data: list[dict] | None = None,
    accuracy_trend: list[dict] | None = None,
    roi_trend: list[dict] | None = None,
) -> tuple[str, str, list[str]]:
    """Generate a note.com accuracy report article.

    Args:
        race_date: The date of the races (YYYY-MM-DD)
        records: List of accuracy records from get_accuracy_for_date()
        stats: Cumulative stats from get_stats()
        roi_stats: Optional ROI stats for the date
        related_links: Optional related article links for cross-linking
        chart_url: Optional URL of uploaded stats chart image
        hit_analyses: Optional dict mapping (stadium, race) -> analysis text
        results_data: Optional list of result dicts for daily trend analysis
        accuracy_trend: Optional 30-day accuracy trend for text-based chart
        roi_trend: Optional 30-day ROI trend for text-based chart

    Returns:
        Tuple of (title, html_body, hashtags)
    """
    total = len(records)
    hit_1st = sum(1 for r in records if r["hit_1st"])
    hit_tri = sum(1 for r in records if r["hit_trifecta"])
    hit_1st_pct = round(hit_1st / total * 100) if total else 0

    venue_names = _venue_names_from_records(records)
    venue_str = _format_venue_list(venue_names)
    num_venues = len(venue_names)
    date_short = _format_date_short(race_date)

    # ── Dynamic title based on results ──
    max_payout = max(
        (r.get("trifecta_payout", 0) for r in records if r["hit_trifecta"]),
        default=0,
    )
    if max_payout >= 10000:
        title = (
            f"万舟的中！競艇AI予想 結果｜{venue_str}全{num_venues}場"
            f"【3連単{hit_tri}本】{date_short}"
        )
    elif hit_tri >= 5:
        title = (
            f"3連単{hit_tri}本的中！競艇AI予想 結果｜{venue_str}全{num_venues}場"
            f" {date_short}"
        )
    elif hit_1st_pct >= 50:
        title = (
            f"的中率{hit_1st_pct}%！競艇AI予想 結果｜{venue_str}全{num_venues}場"
            f" {date_short}"
        )
    else:
        title = (
            f"競艇AI予想 結果｜{venue_str}全{num_venues}場"
            f"【的中率{hit_1st_pct}%】{date_short}"
        )

    html_body = _build_accuracy_html(
        race_date, records, stats, roi_stats=roi_stats, related_links=related_links,
        chart_url=chart_url, hit_analyses=hit_analyses, results_data=results_data,
        accuracy_trend=accuracy_trend, roi_trend=roi_trend,
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

    # C1: Follow CTA at top (grades = highest traffic article)
    parts.append(
        "<p><strong>◎ フォローすると毎朝7:30にAI予測が届きます</strong></p>"
    )

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
    parts.append("<h3>◆ 本日のポイント</h3>")
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
        parts.append("<h3>◆ 注目レース TOP3</h3>")
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
        parts.append("<h3>◆ Sランクの詳細予測を見るには</h3>")
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

    # E1: Dynamic about section
    parts.append(_build_about_section(stats))
    parts.append("<h3>◆ 注意事項</h3>")
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
        items.append(f"<li>◇ {label} → {article['note_url']}</li>")
    if not items:
        return ""
    return f"<h3>◆ 関連記事</h3>\n<ul>{''.join(items)}</ul>"


# ── Membership upsell ─────────────────────────────────────────


def _membership_upsell() -> str:
    """Build membership upsell HTML with config-driven price."""
    price = config.NOTE_MEMBERSHIP_PRICE
    article_price = config.NOTE_ARTICLE_PRICE
    daily = round(price / 30)
    return (
        "<h3>◆ メンバーシップのご案内</h3>"
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

    # Summary (B3: pseudo-table)
    parts.append("<h3>◆ サマリー</h3>")
    total_races_30d = sum(r["total"] for r in accuracy_trend)
    hit_1st_30d = sum(r["hit_1st"] for r in accuracy_trend)
    hit_tri_30d = sum(r["hit_tri"] for r in accuracy_trend)
    rate_1st = round(hit_1st_30d / total_races_30d * 100) if total_races_30d > 0 else 0
    rate_tri = round(hit_tri_30d / total_races_30d * 100) if total_races_30d > 0 else 0
    parts.append(
        "<ul>"
        f"<li>総予測 ………… <strong>{total_races_30d}レース</strong></li>"
        f"<li>1着的中率 …… <strong>{rate_1st}%</strong></li>"
        f"<li>3連単的中率 … <strong>{rate_tri}%</strong></li>"
        f"<li>ROI（回収率）… <strong>{roi_pct}%</strong></li>"
        "</ul>"
    )

    # Daily breakdown (last 7 days) (B3: ul/li format)
    parts.append("<h3>◆ 日別実績（直近7日）</h3>")
    daily_items: list[str] = []
    for acc in accuracy_trend[:7]:
        d = acc["date"]
        date_short = _format_date_short(d)
        pct = round(acc["hit_1st_rate"] * 100)
        roi_day = next((r for r in roi_trend if r["date"] == d), None)
        roi_label = f"｜ROI {round(roi_day['roi'] * 100)}%" if roi_day else ""
        daily_items.append(
            f"<li><strong>{date_short}</strong>　"
            f"{acc['total']}R → 1着{acc['hit_1st']}的中（{pct}%）{roi_label}</li>"
        )
    parts.append(f"<ul>{''.join(daily_items)}</ul>")

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
        parts.append("<h3>◆ トレンド分析</h3>")
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

    # E1: Dynamic about section
    parts.append(_build_about_section(stats))
    parts.append("<h3>◆ 注意事項</h3>")
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
        parts.append("<h3>◆ 午前のハイライト</h3>")
        for r in tri_hits:
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            parts.append(
                f"<p><strong>{stadium} {r['race_number']}R — 3連単的中!</strong> "
                f"予測: {r['predicted_trifecta']} → 結果: {r['actual_trifecta']}</p>"
            )

    # C2: Afternoon CTA
    parts.append("<hr>")
    parts.append("<h3>◆ 午後のレースについて</h3>")
    parts.append(
        "<p><strong>午後もSランクレースを中心に予測を配信中。</strong>"
        "最終結果は夜の結果レポートでまとめてお届けします。</p>"
    )
    parts.append(
        "<p>フォローしておくと、毎朝7:30にAI予測が届きます。"
        "予測→結果→検証を<strong>365日毎日</strong>自動で回し続けるAI予想です。</p>"
    )

    # Related articles
    if related_links:
        related = _build_related_articles("midday", related_links)
        if related:
            parts.append(related)

    # E1: Dynamic about section
    parts.append(_build_about_section())
    parts.append("<h3>◆ 注意事項</h3>")
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

    parts.append("<h3>◆ メンバー特典</h3>")
    parts.append(
        "<ul>"
        f"<li>毎朝Sランク全レースの詳細買い目（通常¥{config.NOTE_ARTICLE_PRICE}/記事）</li>"
        "<li>週次実績レポート</li>"
        "<li>優先お知らせ配信</li>"
        "</ul>"
    )

    parts.append("<h3>◆ 料金</h3>")
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

    # E1: Dynamic about
    parts.append(_build_about_section(stats))
    parts.append("<h3>◆ 注意事項</h3>")
    parts.append(f"<p>{DISCLAIMER}</p>")

    html_body = "\n".join(parts)
    hashtags = _build_hashtags(article_type="prediction")

    return title, html_body, hashtags
