"""Tests for CLI commands using Click's CliRunner."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from boatrace_ai.cli import _fetch_odds_safe, _parse_date, cli
from boatrace_ai.data.models import PredictionResult, ProgramsResponse, ResultsResponse


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def mock_init_db():
    """Don't touch real DB during CLI tests."""
    with patch("boatrace_ai.cli.init_db"):
        yield


# ── _parse_date ─────────────────────────────────────────


def test_parse_date_none() -> None:
    assert _parse_date(None) is None


def test_parse_date_valid() -> None:
    assert _parse_date("2026-02-28") == date(2026, 2, 28)


def test_parse_date_invalid() -> None:
    with pytest.raises(click.BadParameter, match="日付の形式が不正"):
        _parse_date("2026/02/28")


def test_parse_date_garbage() -> None:
    with pytest.raises(click.BadParameter):
        _parse_date("not-a-date")


# ── CLI group ───────────────────────────────────────────


def test_cli_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ボートレースAI予想システム" in result.output


def test_predict_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["predict", "--help"])
    assert result.exit_code == 0
    assert "today" in result.output
    assert "race" in result.output


def test_results_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["results", "--help"])
    assert result.exit_code == 0
    assert "fetch" in result.output
    assert "check" in result.output


# ── predict today ───────────────────────────────────────


def test_predict_today_dry_run(runner: CliRunner, programs_json: dict) -> None:
    programs = ProgramsResponse.model_validate(programs_json)

    with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs):
        result = runner.invoke(cli, ["predict", "today", "--stadium", "1", "--dry-run"])
        assert result.exit_code == 0
        assert "予測対象" in result.output


def test_predict_today_no_races(runner: CliRunner, programs_json: dict) -> None:
    programs = ProgramsResponse.model_validate(programs_json)

    with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs):
        result = runner.invoke(cli, ["predict", "today", "--stadium", "24", "--dry-run"])
        # Stadium 24 likely not in our 2-race fixture
        assert result.exit_code == 0


def test_predict_today_invalid_stadium(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["predict", "today", "--stadium", "99"])
    assert result.exit_code != 0
    assert "not in the range" in result.output


def test_predict_today_fetch_error(runner: CliRunner) -> None:
    with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, side_effect=Exception("Network error")):
        result = runner.invoke(cli, ["predict", "today", "--dry-run"])
        assert result.exit_code == 0  # error is displayed, not raised
        assert "エラー" in result.output


# ── predict race ────────────────────────────────────────


def test_predict_race_invalid_stadium(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["predict", "race", "-s", "0", "-r", "1"])
    assert result.exit_code != 0
    assert "not in the range" in result.output


def test_predict_race_invalid_race_number(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["predict", "race", "-s", "1", "-r", "13"])
    assert result.exit_code != 0
    assert "not in the range" in result.output


def test_predict_race_invalid_date(runner: CliRunner) -> None:
    with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock):
        result = runner.invoke(cli, ["predict", "race", "-s", "1", "-r", "1", "-d", "invalid"])
        # BadParameter is caught by Click and exits with code 2
        assert result.exit_code == 2
        assert "日付の形式が不正" in result.output


# ── results fetch ───────────────────────────────────────


def test_results_fetch(runner: CliRunner, results_json: dict) -> None:
    results_resp = ResultsResponse.model_validate(results_json)

    with patch("boatrace_ai.cli.fetch_results", new_callable=AsyncMock, return_value=results_resp):
        with patch("boatrace_ai.cli.save_result"):
            result = runner.invoke(cli, ["results", "fetch", "2026-02-27"])
            assert result.exit_code == 0
            assert "保存しました" in result.output


def test_results_fetch_error(runner: CliRunner) -> None:
    with patch("boatrace_ai.cli.fetch_results", new_callable=AsyncMock, side_effect=Exception("timeout")):
        result = runner.invoke(cli, ["results", "fetch"])
        assert result.exit_code == 0
        assert "エラー" in result.output


# ── results check ───────────────────────────────────────


def test_results_check_empty(runner: CliRunner) -> None:
    with patch("boatrace_ai.cli.check_accuracy", return_value=[]), \
         patch("boatrace_ai.cli.check_virtual_bets", return_value=[]):
        result = runner.invoke(cli, ["results", "check"])
        assert result.exit_code == 0
        assert "比較可能なレースがありません" in result.output


def test_results_check_with_data(runner: CliRunner) -> None:
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
        }
    ]
    with patch("boatrace_ai.cli.check_accuracy", return_value=records), \
         patch("boatrace_ai.cli.check_virtual_bets", return_value=[]):
        result = runner.invoke(cli, ["results", "check"])
        assert result.exit_code == 0
        assert "今回の比較" in result.output


# ── stats ───────────────────────────────────────────────


def test_stats_empty(runner: CliRunner) -> None:
    stats = {"total_races": 0, "hit_1st": 0, "hit_1st_rate": 0.0, "hit_trifecta": 0, "hit_trifecta_rate": 0.0}
    with patch("boatrace_ai.cli.get_stats", return_value=stats):
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "統計データがありません" in result.output


def test_stats_with_data(runner: CliRunner) -> None:
    stats = {"total_races": 50, "hit_1st": 15, "hit_1st_rate": 0.3, "hit_trifecta": 2, "hit_trifecta_rate": 0.04}
    with patch("boatrace_ai.cli.get_stats", return_value=stats):
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "精度レポート" in result.output


# ── _fetch_odds_safe ─────────────────────────────────────


def _make_race(stadium: int = 1, race_num: int = 1, race_date: str = "2026-03-04"):
    """Create a minimal race-like object for testing."""
    return SimpleNamespace(
        race_stadium_number=stadium,
        race_number=race_num,
        race_date=race_date,
    )


def test_fetch_odds_safe_success() -> None:
    """Successful odds fetch returns OddsData and caches to DB."""
    from boatrace_ai.data.odds import OddsData

    mock_odds = OddsData(
        win={1: 2.3, 2: 8.5},
        exacta={"1-2": 15.0},
        fetched_at="2026-03-04T07:30:00",
    )
    race = _make_race()

    with patch("boatrace_ai.data.odds.fetch_odds", new_callable=AsyncMock, return_value=mock_odds):
        with patch("boatrace_ai.cli.save_race_odds") as mock_save:
            result = asyncio.run(_fetch_odds_safe(race))

    assert result is mock_odds
    mock_save.assert_called_once()
    args = mock_save.call_args
    assert args[0][0] == "2026-03-04"  # race_date
    assert args[0][1] == 1  # stadium_number
    assert args[0][2] == 1  # race_number


def test_fetch_odds_safe_returns_none_on_failure() -> None:
    """Network failure returns None (graceful degradation)."""
    race = _make_race()

    with patch("boatrace_ai.data.odds.fetch_odds", new_callable=AsyncMock, side_effect=Exception("timeout")):
        result = asyncio.run(_fetch_odds_safe(race))

    assert result is None


def test_fetch_odds_safe_returns_none_when_no_odds() -> None:
    """fetch_odds returning None is passed through without caching."""
    race = _make_race()

    with patch("boatrace_ai.data.odds.fetch_odds", new_callable=AsyncMock, return_value=None):
        with patch("boatrace_ai.cli.save_race_odds") as mock_save:
            result = asyncio.run(_fetch_odds_safe(race))

    assert result is None
    mock_save.assert_not_called()
