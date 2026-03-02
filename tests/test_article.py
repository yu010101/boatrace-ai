"""Tests for article generation from race predictions."""

from __future__ import annotations

import json
from pathlib import Path

from boatrace_ai.data.models import PredictionResult, ProgramsResponse
from boatrace_ai.publish.article import (
    DISCLAIMER,
    _build_accuracy_html,
    _build_accuracy_markdown,
    _build_hashtags,
    _build_html,
    _build_markdown,
    generate_accuracy_report,
    generate_article,
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
        assert "第1R" in title
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
    def test_contains_date(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "2026-03-01" in html

    def test_contains_hit_rates(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "1着的中率: 66% (2/3)" in html
        assert "3連単的中率: 33% (1/3)" in html

    def test_contains_hit_section(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "的中レース ✅" in html
        assert "✅ 桐生 1R" in html
        assert "3連単的中!" in html

    def test_contains_miss_section(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "不的中レース" in html
        assert "❌ 桐生 2R" in html

    def test_contains_cumulative_stats(self) -> None:
        html = _build_accuracy_html("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "累計成績" in html
        assert "総レース: 48" in html

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
    def test_contains_date(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "2026-03-01" in md

    def test_contains_hit_rates(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "1着的中率: 66% (2/3)" in md
        assert "3連単的中率: 33% (1/3)" in md

    def test_contains_hit_and_miss_sections(self) -> None:
        md = _build_accuracy_markdown("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "的中レース ✅" in md
        assert "不的中レース" in md

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
        assert "AI予測 結果レポート" in title
        assert "2026-03-01" in title

    def test_html_body_no_pay_tag(self) -> None:
        _, html, _ = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "<pay>" not in html

    def test_hashtags_contain_report_tag(self) -> None:
        _, _, hashtags = generate_accuracy_report("2026-03-01", _make_accuracy_records(), _make_stats())
        assert "的中レポート" in hashtags
        assert "AI予測" in hashtags
