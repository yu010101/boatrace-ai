"""Tests for article generation from race predictions."""

from __future__ import annotations

import json
from pathlib import Path

from boatrace_ai.data.models import PredictionResult, ProgramsResponse
from boatrace_ai.publish.article import (
    DISCLAIMER,
    GRADE_MARKERS,
    MEMBERSHIP_UPSELL,
    _RACE_DRAMA,
    _build_about_section,
    _build_accuracy_html,
    _build_accuracy_markdown,
    _build_daily_trends,
    _build_hashtags,
    _build_hit_analysis,
    _build_html,
    _build_loss_analysis,
    _build_markdown,
    _build_opening_hook,
    _build_related_articles,
    _build_tomorrow_preview,
    _build_trend_text,
    generate_accuracy_report,
    generate_article,
    generate_grade_summary_article,
    generate_membership_article,
    generate_midday_report,
    generate_track_record_article,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_prediction() -> PredictionResult:
    return PredictionResult(
        predicted_order=[1, 3, 2, 4, 5, 6],
        confidence=0.72,
        recommended_bets=["3連単 1-3-2", "2連単 1-3"],
        analysis="1号艇がインから逃げ切り。モーター性能が良好。",
    )


def _load_race():
    data = json.loads((FIXTURES_DIR / "programs_sample.json").read_text())
    programs = ProgramsResponse.model_validate(data)
    return programs.programs[0]


# ── _build_html (note.com-compatible) ─────────────────────


class TestBuildHtml:
    def test_uses_h2_not_h1(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "<h1>" not in html
        assert "<h2>" in html

    def test_contains_title_with_stadium_and_race(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "桐生競艇 第1R AI予測" in html

    def test_predicted_order_in_separate_p_tags(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "<p><strong>1着: 1号艇</strong>" in html
        assert "<p><strong>2着: 3号艇</strong>" in html
        assert "<p><strong>3着: 2号艇</strong>" in html

    def test_confidence_is_bold_text_not_heading(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "<p><strong>信頼度: 72%</strong></p>" in html

    def test_recommended_bets_as_ul(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "<ul>" in html
        assert "<li>3連単 1-3-2</li>" in html
        assert "<li>2連単 1-3</li>" in html

    def test_contains_pay_tag(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "<pay>" in html

    def test_free_section_before_pay(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        pay_idx = html.index("<pay>")
        assert html.index("予測着順") < pay_idx
        assert html.index("信頼度") < pay_idx
        assert html.index("推奨買い目") < pay_idx

    def test_paid_section_after_pay(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        pay_idx = html.index("<pay>")
        assert html.index("AI詳細分析") > pay_idx
        assert html.index("出走表データ") > pay_idx
        assert html.index("注意事項") > pay_idx

    def test_contains_analysis(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert prediction.analysis in html

    def test_boat_data_as_p_tags_not_table(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        # No <table> tag
        assert "<table>" not in html
        # Each boat with number and name
        for boat in race.boats:
            assert f"{boat.racer_boat_number}号艇" in html
            assert boat.racer_name in html

    def test_contains_disclaimer(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert DISCLAIMER in html

    def test_contains_full_predicted_order(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "1 → 3 → 2 → 4 → 5 → 6" in html

    def test_contains_hr_separator(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction)
        assert "<hr>" in html


# ── _build_markdown (CLI preview) ─────────────────────────


class TestBuildMarkdown:
    def test_contains_title(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        md = _build_markdown(race, prediction)
        assert "桐生競艇 第1R AI予測" in md

    def test_uses_h2_not_h1(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        md = _build_markdown(race, prediction)
        assert md.startswith("## ")
        assert "\n# " not in md

    def test_contains_racer_names(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        md = _build_markdown(race, prediction)
        for boat in race.boats:
            assert boat.racer_name in md


# ── _build_hashtags ────────────────────────────────────────


class TestBuildHashtags:
    def test_contains_anchor_tags(self) -> None:
        race = _load_race()
        tags = _build_hashtags(race)
        assert "水理AI" in tags
        assert "AI競艇予想" in tags

    def test_tag_count_within_range(self) -> None:
        race = _load_race()
        tags = _build_hashtags(race)
        assert 4 <= len(tags) <= 6

    def test_tags_vary_between_calls(self) -> None:
        race = _load_race()
        results = [tuple(_build_hashtags(race)) for _ in range(20)]
        # With randomization, not all calls should return the same set
        assert len(set(results)) > 1


# ── generate_article ───────────────────────────────────────


class TestGenerateArticle:
    def test_returns_tuple_of_three(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        result = generate_article(race, prediction)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_title_format(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        title, _, _ = generate_article(race, prediction)
        assert "桐生競艇" in title
        assert "1R" in title
        assert "AI" in title
        assert "AI予想" in title

    def test_html_body_contains_pay(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        _, html, _ = generate_article(race, prediction)
        assert "<pay>" in html
        assert "<h2>" in html

    def test_html_body_no_table(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        _, html, _ = generate_article(race, prediction)
        assert "<table>" not in html

    def test_hashtags_is_list(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        _, _, hashtags = generate_article(race, prediction)
        assert isinstance(hashtags, list)
        assert len(hashtags) >= 3

    def test_free_mode_no_pay_tag(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        _, html, _ = generate_article(race, prediction, free=True)
        assert "<pay>" not in html
        assert "有料エリア" not in html

    def test_free_mode_still_has_content(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        _, html, _ = generate_article(race, prediction, free=True)
        assert "AI詳細分析" in html
        assert "出走表データ" in html
        assert prediction.analysis in html


# ── Free mode ─────────────────────────────────────────────


class TestFreeMode:
    def test_html_no_pay_tag(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction, free=True)
        assert "<pay>" not in html
        assert "有料エリア" not in html
        assert "<hr>" not in html

    def test_html_still_has_all_content(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        html = _build_html(race, prediction, free=True)
        assert "AI詳細分析" in html
        assert "出走表データ" in html
        assert DISCLAIMER in html

    def test_markdown_no_paywall_text(self) -> None:
        race = _load_race()
        prediction = _make_prediction()
        md = _build_markdown(race, prediction, free=True)
        assert "有料エリア" not in md
        assert "AI詳細分析" in md


# ── Accuracy report ───────────────────────────────────────


def _make_accuracy_records() -> list[dict]:
    return [
        {
            "race_date": "2026-03-01",
            "stadium_number": 1,
            "race_number": 1,
            "predicted_1st": 1,
            "actual_1st": 1,
            "hit_1st": True,
            "predicted_trifecta": "1-3-2",
            "actual_trifecta": "1-3-2",
            "hit_trifecta": True,
        },
        {
            "race_date": "2026-03-01",
            "stadium_number": 1,
            "race_number": 2,
            "predicted_1st": 1,
            "actual_1st": 4,
            "hit_1st": False,
            "predicted_trifecta": "1-3-2",
            "actual_trifecta": "4-1-5",
            "hit_trifecta": False,
        },
        {
            "race_date": "2026-03-01",
            "stadium_number": 6,
            "race_number": 3,
            "predicted_1st": 1,
            "actual_1st": 1,
            "hit_1st": True,
            "predicted_trifecta": "1-2-3",
            "actual_trifecta": "1-5-3",
            "hit_trifecta": False,
        },
    ]


def _make_stats() -> dict:
    return {
        "total_races": 48,
        "hit_1st": 13,
        "hit_1st_rate": 0.27,
        "hit_trifecta": 2,
        "hit_trifecta_rate": 0.04,
    }


class TestAccuracyReportHtml:
    def test_contains_summary(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "ボートレースAI予想 本日の結果" in html

    def test_contains_hit_rates(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "1着的中" in html
        assert "2/3" in html
        assert "67%" in html
        assert "3連単的中" in html
        assert "1/3" in html
        assert "33%" in html

    def test_contains_highlight_section(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "3連単的中ハイライト" in html
        assert "桐生 1R" in html
        assert "3連単" in html

    def test_contains_hit_list_by_venue(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "的中レース一覧" in html

    def test_contains_cumulative_stats(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "累計実績" in html
        assert "48" in html
        assert "総予測レース" in html

    def test_uses_h2_not_h1(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "<h1>" not in html
        assert "<h2>" in html

    def test_no_table_tag(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "<table>" not in html

    def test_contains_disclaimer(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert DISCLAIMER in html


class TestAccuracyReportMarkdown:
    def test_contains_summary(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "本日の結果サマリー" in md

    def test_contains_hit_rates(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "1着的中: 2/3 (67%)" in md
        assert "3連単的中: 1/3 (33%)" in md

    def test_contains_highlight_and_hit_list(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "本日のハイライト" in md
        assert "的中レース一覧" in md

    def test_uses_h2_not_h1(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert md.startswith("## ")
        assert "\n# " not in md


class TestGenerateAccuracyReport:
    def test_returns_tuple_of_three(self) -> None:
        result = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_title_format(self) -> None:
        title, _, _ = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "AI" in title
        assert "3/1" in title
        assert "的中率" in title
        assert "競艇AI予想" in title

    def test_html_body_no_pay_tag(self) -> None:
        _, html, _ = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "<pay>" not in html

    def test_hashtags_contain_anchor_tags(self) -> None:
        _, _, hashtags = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "水理AI" in hashtags
        assert "AI競艇予想" in hashtags


# ── Hashtag article_type ─────────────────────────────────────


class TestHashtagsByArticleType:
    def test_anchor_tags_always_present(self) -> None:
        for article_type in ("prediction", "results", "track_record", "midday"):
            tags = _build_hashtags(article_type=article_type)
            assert "水理AI" in tags
            assert "AI競艇予想" in tags

    def test_tag_count_in_range(self) -> None:
        for article_type in ("prediction", "results", "track_record", "midday"):
            tags = _build_hashtags(article_type=article_type)
            assert 4 <= len(tags) <= 6

    def test_max_tags_with_venues(self) -> None:
        race = _load_race()
        tags = _build_hashtags(race, venue_names=["桐生", "戸田", "江戸川"], article_type="prediction")
        assert len(tags) <= 8  # anchors + up to max hashtag count


# ── Related articles ──────────────────────────────────────────


class TestBuildRelatedArticles:
    def test_builds_links(self) -> None:
        links = {
            "grades": {"note_url": "https://note.com/suiri_ai/n/abc", "title": "grades"},
            "results": {"note_url": "https://note.com/suiri_ai/n/def", "title": "results"},
        }
        html = _build_related_articles("midday", links)
        assert "関連記事" in html
        assert "https://note.com/suiri_ai/n/abc" in html
        assert "https://note.com/suiri_ai/n/def" in html

    def test_excludes_current_type(self) -> None:
        links = {
            "grades": {"note_url": "https://note.com/suiri_ai/n/abc", "title": "grades"},
        }
        html = _build_related_articles("grades", links)
        assert html == ""

    def test_empty_links(self) -> None:
        html = _build_related_articles("midday", {})
        assert html == ""


# ── Track record article ─────────────────────────────────────


def _make_accuracy_trend() -> list[dict]:
    return [
        {"date": "2026-03-05", "total": 132, "hit_1st": 74, "hit_1st_rate": 0.56, "hit_tri": 3, "hit_tri_rate": 0.02},
        {"date": "2026-03-04", "total": 130, "hit_1st": 68, "hit_1st_rate": 0.52, "hit_tri": 2, "hit_tri_rate": 0.015},
        {"date": "2026-03-03", "total": 128, "hit_1st": 65, "hit_1st_rate": 0.51, "hit_tri": 1, "hit_tri_rate": 0.008},
    ]


def _make_roi_trend() -> list[dict]:
    return [
        {"date": "2026-03-05", "bets": 20, "invested": 20000, "payout": 17800, "roi": 0.89},
        {"date": "2026-03-04", "bets": 18, "invested": 18000, "payout": 13500, "roi": 0.75},
    ]


class TestTrackRecordArticle:
    def test_returns_tuple_of_three(self) -> None:
        result = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_title_contains_keywords(self) -> None:
        title, _, _ = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert "AI" in title
        assert "実績" in title

    def test_html_contains_summary(self) -> None:
        _, html, _ = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert "サマリー" in html
        assert "日別実績" in html
        assert "1着" in html

    def test_html_no_h1_no_table(self) -> None:
        _, html, _ = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert "<h1>" not in html
        assert "<table>" not in html

    def test_html_contains_membership_upsell(self) -> None:
        _, html, _ = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert "メンバーシップ" in html

    def test_hashtags_contain_anchors(self) -> None:
        _, _, hashtags = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert "水理AI" in hashtags
        assert "AI競艇予想" in hashtags


# ── Midday report ─────────────────────────────────────────────


class TestMiddayReport:
    def test_returns_tuple_of_three(self) -> None:
        result = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_title_contains_keywords(self) -> None:
        title, _, _ = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "午前" in title
        assert "AI" in title
        assert "3/1" in title

    def test_html_contains_summary(self) -> None:
        _, html, _ = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "午前の部 結果速報" in html
        assert "1着的中" in html

    def test_html_contains_highlight(self) -> None:
        _, html, _ = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "午前のハイライト" in html
        assert "1-3-2" in html  # predicted trifecta in highlight

    def test_html_no_pay_tag(self) -> None:
        _, html, _ = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "<pay>" not in html

    def test_hashtags_contain_anchors(self) -> None:
        _, _, hashtags = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "水理AI" in hashtags
        assert "AI競艇予想" in hashtags


# ── Membership article ────────────────────────────────────────


class TestMembershipArticle:
    def test_returns_tuple_of_three(self) -> None:
        result = generate_membership_article(_make_stats())
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_title_contains_keywords(self) -> None:
        title, _, _ = generate_membership_article(_make_stats())
        assert "メンバーシップ" in title
        assert "AI" in title

    def test_html_contains_benefits(self) -> None:
        _, html, _ = generate_membership_article(_make_stats())
        assert "メンバー特典" in html
        assert "¥1,000" in html
        assert "Sランク" in html

    def test_html_contains_track_record(self) -> None:
        _, html, _ = generate_membership_article(_make_stats())
        assert "累計実績" in html

    def test_html_no_pay_tag(self) -> None:
        _, html, _ = generate_membership_article(_make_stats())
        assert "<pay>" not in html


# ── Accuracy report includes membership upsell ───────────────


class TestAccuracyReportMembershipUpsell:
    def test_accuracy_html_includes_membership(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "メンバーシップ" in html


# ── Hit analysis (施策1) ─────────────────────────────────────


class TestBuildHitAnalysis:
    def test_with_prediction_and_result(self) -> None:
        record = {
            "stadium_number": 1, "race_number": 1,
            "hit_trifecta": True, "trifecta_payout": 15000,
            "predicted_trifecta": "1-3-2", "actual_trifecta": "1-3-2",
        }
        prediction = {
            "confidence": 0.72,
            "analysis": "1号艇がインから逃げ切り。モーター性能が良好。",
            "predicted_order": [1, 3, 2],
            "technique_number": None, "wind": None, "wave": None,
        }
        result = {"technique_number": 1, "wind": 3, "wave": 2}
        text = _build_hit_analysis(record, prediction, result)
        assert "72%" in text
        assert "逃げ" in text
        assert "万舟" in text

    def test_no_prediction(self) -> None:
        record = {"hit_trifecta": True, "trifecta_payout": 500}
        text = _build_hit_analysis(record, None, None)
        assert "¥500" in text

    def test_empty_data(self) -> None:
        record = {"hit_trifecta": True, "trifecta_payout": 0}
        text = _build_hit_analysis(record, None, None)
        assert text == ""

    def test_analysis_in_highlight(self) -> None:
        """Hit analyses are embedded in accuracy HTML highlight section."""
        records = _make_accuracy_records()
        # Add payout to make it a valid trifecta hit
        records[0]["trifecta_payout"] = 5000
        analyses = {(1, 1): "（AIの信頼度は72%。決まり手は「逃げ」）"}
        html = _build_accuracy_html(
            "2026-03-01", records, _make_stats(),
            hit_analyses=analyses,
        )
        assert "AIの信頼度は72%" in html


# ── Daily trends (施策3) ─────────────────────────────────────


class TestBuildDailyTrends:
    def _make_results_data(self) -> list[dict]:
        return [
            {"stadium_number": 1, "race_number": i, "actual_order": [1, 3, 2, 4, 5, 6],
             "actual_1st": 1, "technique_number": 1, "wind": 3, "wave": 2}
            for i in range(1, 7)
        ] + [
            {"stadium_number": 6, "race_number": i, "actual_order": [3, 1, 2, 4, 5, 6],
             "actual_1st": 3, "technique_number": 3, "wind": 5, "wave": 3}
            for i in range(1, 5)
        ]

    def test_contains_technique_distribution(self) -> None:
        trends = _build_daily_trends(_make_accuracy_records(), self._make_results_data())
        assert "決まり手" in trends
        assert "逃げ" in trends

    def test_contains_inner_course_rate(self) -> None:
        trends = _build_daily_trends(_make_accuracy_records(), self._make_results_data())
        assert "1号艇1着率" in trends

    def test_empty_results(self) -> None:
        trends = _build_daily_trends(_make_accuracy_records(), [])
        assert trends == ""

    def test_trends_in_accuracy_html(self) -> None:
        """Daily trends appear in accuracy HTML when results_data is provided."""
        results_data = self._make_results_data()
        html = _build_accuracy_html(
            "2026-03-01", _make_accuracy_records(), _make_stats(),
            results_data=results_data,
        )
        assert "本日の傾向分析" in html
        assert "決まり手" in html


# ── Chart URL in accuracy HTML (施策2) ───────────────────────


class TestChartInAccuracyHtml:
    def test_chart_image_embedded(self) -> None:
        html = _build_accuracy_html(
            "2026-03-01", _make_accuracy_records(), _make_stats(),
            chart_url="https://assets.note.com/chart123.png",
        )
        assert '<img src="https://assets.note.com/chart123.png"' in html

    def test_no_chart_no_img(self) -> None:
        html = _build_accuracy_html(
            "2026-03-01", _make_accuracy_records(), _make_stats(),
        )
        assert "<img" not in html

    def test_text_trend_fallback(self) -> None:
        """When no chart_url but accuracy_trend is provided, text trend appears."""
        html = _build_accuracy_html(
            "2026-03-01", _make_accuracy_records(), _make_stats(),
            accuracy_trend=_make_accuracy_trend(), roi_trend=_make_roi_trend(),
        )
        assert "直近7日間の推移" in html
        assert "■" in html  # Unicode bar

    def test_trend_text_contains_dates(self) -> None:
        text = _build_trend_text(_make_accuracy_trend(), _make_roi_trend())
        assert "3/5" in text
        assert "3/4" in text
        assert "ROI" in text


# ── Title variation (施策4) ──────────────────────────────────


class TestTitleVariation:
    def _make_records_with_payouts(self, payout: int, hit_count: int = 1) -> list[dict]:
        records = []
        for i in range(hit_count):
            records.append({
                "race_date": "2026-03-01", "stadium_number": 1, "race_number": i + 1,
                "predicted_1st": 1, "actual_1st": 1, "hit_1st": True,
                "predicted_trifecta": "1-3-2", "actual_trifecta": "1-3-2",
                "hit_trifecta": True, "trifecta_payout": payout,
            })
        # Add some non-hits
        for i in range(3):
            records.append({
                "race_date": "2026-03-01", "stadium_number": 6, "race_number": i + 1,
                "predicted_1st": 1, "actual_1st": 4, "hit_1st": False,
                "predicted_trifecta": "1-3-2", "actual_trifecta": "4-1-5",
                "hit_trifecta": False, "trifecta_payout": 0,
            })
        return records

    def test_manshuu_title(self) -> None:
        """High payout (>=10000) triggers 万舟 title."""
        records = self._make_records_with_payouts(15000)
        title, _, _ = generate_accuracy_report("2026-03-01", records, _make_stats())
        assert "万舟" in title

    def test_many_trifecta_hits_title(self) -> None:
        """5+ trifecta hits triggers count-based title."""
        records = self._make_records_with_payouts(500, hit_count=6)
        title, _, _ = generate_accuracy_report("2026-03-01", records, _make_stats())
        assert "6本的中" in title

    def test_high_hit_rate_title(self) -> None:
        """>=50% hit rate triggers hit-rate title."""
        records = [
            {"race_date": "2026-03-01", "stadium_number": 1, "race_number": i,
             "predicted_1st": 1, "actual_1st": 1, "hit_1st": True,
             "predicted_trifecta": "1-3-2", "actual_trifecta": "4-1-5",
             "hit_trifecta": False, "trifecta_payout": 0}
            for i in range(1, 4)
        ] + [
            {"race_date": "2026-03-01", "stadium_number": 6, "race_number": 1,
             "predicted_1st": 1, "actual_1st": 4, "hit_1st": False,
             "predicted_trifecta": "1-3-2", "actual_trifecta": "4-1-5",
             "hit_trifecta": False, "trifecta_payout": 0}
        ]
        title, _, _ = generate_accuracy_report("2026-03-01", records, _make_stats())
        assert "75%" in title

    def test_default_title(self) -> None:
        """Low results use default title format."""
        title, _, _ = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "競艇AI予想 結果" in title
        assert "的中率" in title


# ── Opening hook (施策A1) ─────────────────────────────────


class TestOpeningHook:
    def test_manshuu_hook(self) -> None:
        hook = _build_opening_hook(50, 3, 100, max_payout=15000)
        assert "万舟" in hook

    def test_good_day_hook(self) -> None:
        hook = _build_opening_hook(55, 6, 100, roi_pct=110)
        assert "好調" in hook

    def test_struggle_hook(self) -> None:
        hook = _build_opening_hook(35, 1, 100)
        assert "苦戦" in hook

    def test_stable_hook(self) -> None:
        hook = _build_opening_hook(52, 2, 100)
        assert "安定" in hook

    def test_default_hook(self) -> None:
        hook = _build_opening_hook(42, 2, 100)
        assert "まとめました" in hook

    def test_hook_in_accuracy_html(self) -> None:
        """Opening hook appears in accuracy report HTML."""
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        # 67% hit rate -> stable hook
        assert "安定" in html


# ── Loss analysis (施策A3) ────────────────────────────────


class TestLossAnalysis:
    def _make_bad_records(self) -> list[dict]:
        """Records with <45% hit rate to trigger loss analysis."""
        records = []
        for i in range(10):
            records.append({
                "race_date": "2026-03-01", "stadium_number": 1, "race_number": i + 1,
                "predicted_1st": 1, "actual_1st": 4 if i < 7 else 1,
                "hit_1st": i >= 7,
                "predicted_trifecta": "1-3-2", "actual_trifecta": "4-1-5",
                "hit_trifecta": False, "trifecta_payout": 0,
            })
        return records

    def test_shows_on_bad_day(self) -> None:
        loss = _build_loss_analysis(self._make_bad_records(), [])
        assert "敗因分析" in loss
        assert "苦戦" in loss

    def test_hidden_on_good_day(self) -> None:
        loss = _build_loss_analysis(_make_accuracy_records(), [])
        assert loss == ""

    def test_in_accuracy_html(self) -> None:
        """Loss analysis appears in accuracy HTML on bad days."""
        bad_records = self._make_bad_records()
        html = _build_accuracy_html("2026-03-01", bad_records, _make_stats())
        assert "敗因分析" in html


# ── About section (施策E1) ────────────────────────────────


class TestAboutSection:
    def test_static_fallback(self) -> None:
        about = _build_about_section()
        assert "水理AIとは" in about
        assert "全履歴公開" in about

    def test_with_stats(self) -> None:
        about = _build_about_section(_make_stats())
        assert "48" in about
        assert "累計分析" in about

    def test_in_accuracy_html(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "水理AIとは" in html
        assert "累計分析" in html


# ── Decorations (施策B1) ──────────────────────────────────


class TestDecorations:
    def test_accuracy_html_has_decorations(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "━━" in html
        assert "◆" in html

    def test_related_links_decorated(self) -> None:
        links = {
            "grades": {"note_url": "https://note.com/suiri_ai/n/abc", "title": "grades"},
        }
        html = _build_related_articles("midday", links)
        assert "◇" in html
        assert "<ul>" in html

    def test_track_record_pseudo_table(self) -> None:
        from boatrace_ai.publish.article import _build_track_record
        html = _build_track_record(_make_stats())
        assert "<ul>" in html
        assert "総予測レース" in html
        assert "48" in html


# ── CTA (施策C1/C2) ──────────────────────────────────────


class TestCTA:
    def test_follow_cta_in_accuracy(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "朝7:30" in html
        assert "フォロー" in html

    def test_follow_cta_in_midday(self) -> None:
        _, html, _ = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "フォロー" in html
        assert "365日" in html


# ── v4: D1 Dynamic Titles ──────────────────────────────────


def _make_grades(s_count: int = 3, a_count: int = 5) -> list[dict]:
    grades = []
    for i in range(s_count):
        grades.append({
            "stadium_number": 1,
            "race_number": i + 1,
            "grade": "S",
            "top1_prob": 0.45,
        })
    for i in range(a_count):
        grades.append({
            "stadium_number": 6,
            "race_number": i + 1,
            "grade": "A",
            "top1_prob": 0.35,
        })
    return grades


class TestDynamicTitles:
    def test_grades_title_s_count_high(self) -> None:
        grades = _make_grades(s_count=6)
        title, _, _ = generate_grade_summary_article("2026-03-12", grades)
        assert "Sランク6レース" in title

    def test_grades_title_s_count_normal(self) -> None:
        grades = _make_grades(s_count=2)
        title, _, _ = generate_grade_summary_article("2026-03-12", grades, stats=_make_stats())
        assert "Sランク2レース" in title

    def test_grades_title_no_stats(self) -> None:
        grades = _make_grades(s_count=2)
        title, _, _ = generate_grade_summary_article("2026-03-12", grades)
        assert "Sランク2レース" in title

    def test_track_record_title_dynamic(self) -> None:
        acc_trend = [{"date": f"2026-03-{i:02d}", "total": 48, "hit_1st": 30,
                      "hit_tri": 2, "hit_1st_rate": 0.63} for i in range(1, 8)]
        roi_trend = [{"date": f"2026-03-{i:02d}", "invested": 10000,
                      "payout": 9000, "roi": 0.9} for i in range(1, 8)]
        stats = {**_make_stats(), "hit_1st_rate": 0.55}
        title, _, _ = generate_track_record_article(acc_trend, roi_trend, stats)
        assert "的中率55%" in title

    def test_track_record_title_low_rate(self) -> None:
        acc_trend = [{"date": f"2026-03-{i:02d}", "total": 48, "hit_1st": 10,
                      "hit_tri": 2, "hit_1st_rate": 0.21} for i in range(1, 8)]
        roi_trend = [{"date": f"2026-03-{i:02d}", "invested": 10000,
                      "payout": 9000, "roi": 0.9} for i in range(1, 8)]
        title, _, _ = generate_track_record_article(acc_trend, roi_trend, _make_stats())
        assert "48" in title


# ── v4: B2 Grade Markers ───────────────────────────────────


class TestGradeMarkers:
    def test_markers_defined(self) -> None:
        assert GRADE_MARKERS["S"] == "◎"
        assert GRADE_MARKERS["A"] == "○"
        assert GRADE_MARKERS["B"] == "△"
        assert GRADE_MARKERS["C"] == "✕"

    def test_grade_header_has_marker(self) -> None:
        grades = _make_grades(s_count=2, a_count=3)
        _, html, _ = generate_grade_summary_article("2026-03-12", grades)
        assert "◎ 推奨度Sランク" in html
        assert "○ 推奨度Aランク" in html

    def test_grade_c_marker(self) -> None:
        grades = [{"stadium_number": 1, "race_number": 1, "grade": "C", "top1_prob": 0.15}]
        _, html, _ = generate_grade_summary_article("2026-03-12", grades)
        assert "✕ 推奨度Cランク" in html


# ── v4: D3 Dynamic Hashtags ────────────────────────────────


class TestDynamicHashtags:
    def test_accuracy_hashtags_manshuu(self) -> None:
        records = _make_accuracy_records()
        records[0]["trifecta_payout"] = 15000
        _, _, tags = generate_accuracy_report("2026-03-01", records, _make_stats())
        assert "万舟" in tags

    def test_accuracy_hashtags_roi_high(self) -> None:
        records = _make_accuracy_records()
        roi_stats = {"total_bets": 5, "roi": 1.5, "total_invested": 5000,
                     "total_payout": 7500, "profit": 2500}
        _, _, tags = generate_accuracy_report(
            "2026-03-01", records, _make_stats(), roi_stats=roi_stats,
        )
        assert "回収率100超" in tags

    def test_grades_hashtags_include_free(self) -> None:
        grades = _make_grades()
        _, _, tags = generate_grade_summary_article("2026-03-12", grades)
        assert "無料予想" in tags

    def test_hashtags_dynamic_tags_param(self) -> None:
        tags = _build_hashtags(article_type="results", dynamic_tags=["万舟", "テスト"])
        assert "万舟" in tags
        assert "テスト" in tags


# ── v4: A2 Race Drama ──────────────────────────────────────


class TestRaceDrama:
    def test_drama_templates_exist(self) -> None:
        assert len(_RACE_DRAMA) == 6
        for tech in ["逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"]:
            assert tech in _RACE_DRAMA

    def test_hit_analysis_with_drama(self) -> None:
        record = {"trifecta_payout": 5000}
        result = {"technique_number": 3, "first_place": 4}
        text = _build_hit_analysis(record, None, result)
        assert "まくり" in text
        assert "4号艇" in text

    def test_hit_analysis_makuri_sashi(self) -> None:
        record = {"trifecta_payout": 8000}
        result = {"technique_number": 4, "first_place": 2}
        text = _build_hit_analysis(record, None, result)
        assert "まくり差し" in text
        assert "2号艇" in text

    def test_hit_analysis_nige(self) -> None:
        record = {"trifecta_payout": 3000}
        result = {"technique_number": 1, "first_place": 1}
        text = _build_hit_analysis(record, None, result)
        assert "逃げ切り" in text
        assert "1号艇" in text


# ── v4: C4 Membership Performance ──────────────────────────


class TestMembershipPerformance:
    def test_membership_has_performance(self) -> None:
        stats = {**_make_stats(), "hit_trifecta_count": 15}
        _, html, _ = generate_membership_article(stats)
        assert "直近の実績" in html
        assert "15" in html
        assert "3連単的中" in html

    def test_membership_has_total_races(self) -> None:
        _, html, _ = generate_membership_article(_make_stats())
        assert "分析レース数" in html
        assert "48" in html


# ── v4: A4 Tomorrow Preview ────────────────────────────────


class TestTomorrowPreview:
    def test_preview_shows_hot_venues(self) -> None:
        records = _make_accuracy_records()
        html = _build_tomorrow_preview(records)
        assert "明日の注目" in html
        assert "桐生" in html  # stadium 1, 1/2 hit = 50%

    def test_preview_empty_when_no_hits(self) -> None:
        records = [
            {"stadium_number": 1, "race_number": 1, "hit_1st": False},
            {"stadium_number": 6, "race_number": 2, "hit_1st": False},
        ]
        html = _build_tomorrow_preview(records)
        assert html == ""

    def test_preview_in_accuracy_html(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "明日の注目" in html
