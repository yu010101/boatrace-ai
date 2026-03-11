"""Tests for article generation from race predictions."""

from __future__ import annotations

import json
from pathlib import Path

from boatrace_ai.data.models import PredictionResult, ProgramsResponse
from boatrace_ai.publish.article import (
    DISCLAIMER,
    MEMBERSHIP_UPSELL,
    _build_accuracy_html,
    _build_accuracy_markdown,
    _build_hashtags,
    _build_html,
    _build_markdown,
    _build_related_articles,
    generate_accuracy_report,
    generate_article,
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
        # Each boat as individual <p> with bold boat number
        for boat in race.boats:
            assert f"<strong>{boat.racer_boat_number}号艇</strong>" in html
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
    def test_contains_standard_tags(self) -> None:
        race = _load_race()
        tags = _build_hashtags(race)
        assert "競艇" in tags
        assert "ボートレース" in tags
        assert "AI予測" in tags

    def test_contains_stadium_name(self) -> None:
        race = _load_race()
        tags = _build_hashtags(race)
        assert "桐生" in tags


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
        assert "AI予測" in title
        assert race.race_date in title

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
        assert "1着的中: 2/3 (67%)" in html
        assert "3連単的中: 1/3 (33%)" in html

    def test_contains_highlight_section(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "本日のハイライト" in html
        assert "桐生 1R" in html
        assert "3連単的中!" in html

    def test_contains_hit_list_by_venue(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "的中レース一覧" in html

    def test_contains_cumulative_stats(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "累計実績" in html
        assert "総予測: 48" in html

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

    def test_hashtags_contain_standard_tags(self) -> None:
        _, _, hashtags = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "AI予測" in hashtags
        assert "水理AI" in hashtags


# ── Hashtag article_type ─────────────────────────────────────


class TestHashtagsByArticleType:
    def test_prediction_type(self) -> None:
        tags = _build_hashtags(article_type="prediction")
        assert "競艇予想" in tags
        assert "無料予想" in tags

    def test_results_type(self) -> None:
        tags = _build_hashtags(article_type="results")
        assert "競艇結果" in tags
        assert "的中" in tags

    def test_track_record_type(self) -> None:
        tags = _build_hashtags(article_type="track_record")
        assert "競艇実績" in tags
        assert "回収率推移" in tags

    def test_midday_type(self) -> None:
        tags = _build_hashtags(article_type="midday")
        assert "競艇速報" in tags
        assert "午前結果" in tags

    def test_max_10_tags(self) -> None:
        race = _load_race()
        tags = _build_hashtags(race, venue_names=["桐生", "戸田", "江戸川"], article_type="prediction")
        assert len(tags) <= 10


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

    def test_hashtags_are_track_record_type(self) -> None:
        _, _, hashtags = generate_track_record_article(
            _make_accuracy_trend(), _make_roi_trend(), _make_stats(),
        )
        assert "競艇実績" in hashtags


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
        assert "3連単的中!" in html

    def test_html_no_pay_tag(self) -> None:
        _, html, _ = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "<pay>" not in html

    def test_hashtags_are_midday_type(self) -> None:
        _, _, hashtags = generate_midday_report("2026-03-01", _make_accuracy_records())
        assert "競艇速報" in hashtags


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
        assert "月額¥1,000" in html
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
