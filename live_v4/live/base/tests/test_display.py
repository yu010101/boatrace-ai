"""Tests for Rich display formatting (output captured via StringIO)."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from boatrace_ai.data.models import PredictionResult, ProgramsResponse
from boatrace_ai.display import formatter


def _capture_console() -> tuple[Console, StringIO]:
    """Create a console that writes to a StringIO buffer."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, width=120)
    return con, buf


def test_display_prediction(programs_json: dict) -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        resp = ProgramsResponse.model_validate(programs_json)
        race = resp.programs[0]
        prediction = PredictionResult(
            predicted_order=[1, 3, 2, 5, 4, 6],
            confidence=0.72,
            recommended_bets=["3連単 1-3-2", "2連単 1-3"],
            analysis="1号艇がインから逃げ切り。",
        )

        formatter.display_prediction(race, prediction)
        output = buf.getvalue()

        # Should contain race info
        assert "1R" in output
        # Should contain prediction panel
        assert "AI予測" in output
        assert "1 → 3 → 2 → 5 → 4 → 6" in output
        assert "72%" in output
        assert "1号艇がインから逃げ切り" in output
    finally:
        formatter.console = original_console


def test_display_prediction_low_confidence(programs_json: dict) -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        resp = ProgramsResponse.model_validate(programs_json)
        race = resp.programs[0]
        prediction = PredictionResult(
            predicted_order=[1, 3, 2, 5, 4, 6],
            confidence=0.25,
            recommended_bets=[],
            analysis="混戦模様。",
        )

        formatter.display_prediction(race, prediction)
        output = buf.getvalue()
        assert "25%" in output
    finally:
        formatter.console = original_console


def test_display_accuracy_records() -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        records = [
            {
                "race_date": "2026-02-28",
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
                "race_date": "2026-02-28",
                "stadium_number": 1,
                "race_number": 2,
                "predicted_1st": 1,
                "actual_1st": 3,
                "hit_1st": False,
                "predicted_trifecta": "1-3-2",
                "actual_trifecta": "3-1-2",
                "hit_trifecta": False,
            },
        ]

        formatter.display_accuracy_records(records)
        output = buf.getvalue()

        assert "予測 vs 結果" in output
        assert "桐生" in output
        assert "○" in output
        assert "×" in output
    finally:
        formatter.console = original_console


def test_display_accuracy_records_empty() -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        formatter.display_accuracy_records([])
        output = buf.getvalue()
        assert "比較可能なレースがありません" in output
    finally:
        formatter.console = original_console


def test_display_stats() -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        stats = {
            "total_races": 100,
            "hit_1st": 25,
            "hit_1st_rate": 0.25,
            "hit_trifecta": 3,
            "hit_trifecta_rate": 0.03,
        }
        formatter.display_stats(stats)
        output = buf.getvalue()

        assert "精度レポート" in output
        assert "100" in output
        assert "25.0%" in output
        assert "3.0%" in output
    finally:
        formatter.console = original_console


def test_display_stats_empty() -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        stats = {
            "total_races": 0,
            "hit_1st": 0,
            "hit_1st_rate": 0.0,
            "hit_trifecta": 0,
            "hit_trifecta_rate": 0.0,
        }
        formatter.display_stats(stats)
        output = buf.getvalue()
        assert "統計データがありません" in output
    finally:
        formatter.console = original_console


def test_display_results_saved() -> None:
    buf = StringIO()
    con = Console(file=buf, force_terminal=False, no_color=True, width=120)
    original_console = formatter.console
    formatter.console = con

    try:
        formatter.display_results_saved(42, "2026-02-28")
        output = buf.getvalue()
        assert "2026-02-28" in output
        assert "42" in output
        assert "保存しました" in output
    finally:
        formatter.console = original_console


def test_display_error() -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        formatter.display_error("テストエラーです")
        output = buf.getvalue()
        assert "エラー" in output
        assert "テストエラーです" in output
    finally:
        formatter.console = original_console


def test_display_progress() -> None:
    con, buf = _capture_console()
    original_console = formatter.console
    formatter.console = con

    try:
        formatter.display_progress(3, 12, "桐生 3R 予測中...")
        output = buf.getvalue()
        assert "[3/12]" in output
        assert "桐生 3R 予測中..." in output
    finally:
        formatter.console = original_console
