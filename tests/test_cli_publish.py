"""Tests for CLI publish/note commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from boatrace_ai.cli import cli
from boatrace_ai.data.models import PredictionResult, ProgramsResponse, ResultsResponse


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def mock_init_db():
    """Don't touch real DB during CLI tests."""
    with patch("boatrace_ai.cli.init_db"):
        yield


def _make_prediction() -> PredictionResult:
    return PredictionResult(
        predicted_order=[1, 3, 2, 4, 5, 6],
        confidence=0.72,
        recommended_bets=["3連単 1-3-2", "2連単 1-3"],
        analysis="1号艇がインから逃げ切り。",
    )


# ── note commands ──────────────────────────────────────────


class TestNoteCommands:
    def test_note_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["note", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output
        assert "status" in result.output

    def test_note_login_success(self, runner: CliRunner) -> None:
        with patch("boatrace_ai.cli.NoteClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            result = runner.invoke(cli, ["note", "login"])
            assert result.exit_code == 0
            assert "ログインに成功" in result.output

    def test_note_login_failure(self, runner: CliRunner) -> None:
        with patch("boatrace_ai.cli.NoteClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.login.side_effect = Exception("auth failed")
            mock_cls.return_value = mock_client
            result = runner.invoke(cli, ["note", "login"])
            assert result.exit_code == 0
            assert "エラー" in result.output

    def test_note_status(self, runner: CliRunner) -> None:
        with patch("boatrace_ai.cli.NoteClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status.return_value = {
                "logged_in": True,
                "session_path": "/tmp/session.json",
                "session_exists": True,
            }
            mock_cls.return_value = mock_client
            result = runner.invoke(cli, ["note", "status"])
            assert result.exit_code == 0
            assert "ログイン済み" in result.output

    def test_note_status_not_logged_in(self, runner: CliRunner) -> None:
        with patch("boatrace_ai.cli.NoteClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get_status.return_value = {
                "logged_in": False,
                "session_path": "/tmp/session.json",
                "session_exists": False,
            }
            mock_cls.return_value = mock_client
            result = runner.invoke(cli, ["note", "status"])
            assert result.exit_code == 0
            assert "未ログイン" in result.output


# ── publish commands ───────────────────────────────────────


class TestPublishCommands:
    def test_publish_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["publish", "--help"])
        assert result.exit_code == 0
        assert "today" in result.output
        assert "race" in result.output

    def test_publish_race_dry_run(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)
        prediction = _make_prediction()

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.predict_race_auto", new_callable=AsyncMock, return_value=prediction),
            patch("boatrace_ai.cli.save_prediction"),
        ):
            result = runner.invoke(cli, ["publish", "race", "-s", "1", "-r", "1", "--dry-run"])
            assert result.exit_code == 0
            assert "プレビュー" in result.output

    def test_publish_race_no_race_found(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)

        with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs):
            result = runner.invoke(cli, ["publish", "race", "-s", "24", "-r", "12", "--dry-run"])
            assert result.exit_code == 0
            assert "見つかりません" in result.output

    def test_publish_race_fetch_error(self, runner: CliRunner) -> None:
        with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, side_effect=Exception("Network")):
            result = runner.invoke(cli, ["publish", "race", "-s", "1", "-r", "1"])
            assert result.exit_code == 0
            assert "エラー" in result.output

    def test_publish_race_prediction_error(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.predict_race_auto", new_callable=AsyncMock, side_effect=Exception("AI error")),
        ):
            result = runner.invoke(cli, ["publish", "race", "-s", "1", "-r", "1", "--dry-run"])
            assert result.exit_code == 0
            assert "エラー" in result.output

    def test_publish_race_actual_post(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)
        prediction = _make_prediction()

        mock_note = AsyncMock()
        mock_note.create_and_publish.return_value = {
            "data": {"note_url": "https://note.com/user/n/abc123"}
        }

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.predict_race_auto", new_callable=AsyncMock, return_value=prediction),
            patch("boatrace_ai.cli.save_prediction"),
            patch("boatrace_ai.cli.NoteClient", return_value=mock_note),
        ):
            result = runner.invoke(cli, ["publish", "race", "-s", "1", "-r", "1"])
            assert result.exit_code == 0
            assert "投稿成功" in result.output

    def test_publish_race_invalid_stadium(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["publish", "race", "-s", "0", "-r", "1"])
        assert result.exit_code != 0

    def test_publish_today_dry_run(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)
        prediction = _make_prediction()

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.predict_race_auto", new_callable=AsyncMock, return_value=prediction),
            patch("boatrace_ai.cli.save_prediction"),
        ):
            result = runner.invoke(cli, ["publish", "today", "-s", "1", "--dry-run"])
            assert result.exit_code == 0
            assert "投稿サマリー" in result.output

    def test_publish_today_fetch_error(self, runner: CliRunner) -> None:
        with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, side_effect=Exception("error")):
            result = runner.invoke(cli, ["publish", "today"])
            assert result.exit_code == 0
            assert "エラー" in result.output

    def test_publish_today_no_races(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)

        with patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs):
            result = runner.invoke(cli, ["publish", "today", "-s", "24"])
            assert result.exit_code == 0
            assert "見つかりません" in result.output

    def test_publish_today_login_failure(self, runner: CliRunner, programs_json: dict) -> None:
        programs = ProgramsResponse.model_validate(programs_json)

        mock_note = AsyncMock()
        mock_note.ensure_logged_in.side_effect = Exception("login failed")

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.NoteClient", return_value=mock_note),
        ):
            result = runner.invoke(cli, ["publish", "today", "-s", "1"])
            assert result.exit_code == 0
            assert "エラー" in result.output

    def test_publish_today_free_dry_run(self, runner: CliRunner, programs_json: dict) -> None:
        """--free flag should produce article without paywall."""
        programs = ProgramsResponse.model_validate(programs_json)
        prediction = _make_prediction()

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.predict_race_auto", new_callable=AsyncMock, return_value=prediction),
            patch("boatrace_ai.cli.save_prediction"),
        ):
            result = runner.invoke(cli, ["publish", "today", "-s", "1", "--dry-run", "--free"])
            assert result.exit_code == 0
            assert "プレビュー" in result.output
            # Free mode should NOT have paywall text
            assert "有料エリア" not in result.output

    def test_publish_today_free_shows_mode_label(self, runner: CliRunner, programs_json: dict) -> None:
        """--free flag should show 無料 in the mode label."""
        programs = ProgramsResponse.model_validate(programs_json)
        prediction = _make_prediction()

        with (
            patch("boatrace_ai.cli.fetch_programs", new_callable=AsyncMock, return_value=programs),
            patch("boatrace_ai.cli.predict_race_auto", new_callable=AsyncMock, return_value=prediction),
            patch("boatrace_ai.cli.save_prediction"),
        ):
            result = runner.invoke(cli, ["publish", "today", "-s", "1", "--dry-run", "--free"])
            assert result.exit_code == 0
            assert "無料" in result.output


# ── publish results command ───────────────────────────────


class TestPublishResults:
    def test_publish_results_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["publish", "results", "--help"])
        assert result.exit_code == 0
        assert "的中レポート" in result.output

    def test_publish_results_dry_run(self, runner: CliRunner, results_json: dict) -> None:
        """publish results --dry-run should show accuracy report preview."""
        results_resp = ResultsResponse.model_validate(results_json)

        mock_records = [
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
        ]
        mock_stats = {
            "total_races": 10,
            "hit_1st": 3,
            "hit_1st_rate": 0.3,
            "hit_trifecta": 1,
            "hit_trifecta_rate": 0.1,
        }

        mock_roi = {
            "total_bets": 0, "total_invested": 0, "total_payout": 0,
            "profit": 0, "roi": 0.0, "hit_count": 0, "hit_rate": 0.0,
        }

        with (
            patch("boatrace_ai.cli.fetch_results", new_callable=AsyncMock, return_value=results_resp),
            patch("boatrace_ai.cli.save_result"),
            patch("boatrace_ai.cli.check_accuracy"),
            patch("boatrace_ai.cli.get_accuracy_for_date", return_value=mock_records),
            patch("boatrace_ai.cli.get_stats", return_value=mock_stats),
            patch("boatrace_ai.cli.get_roi_daily", return_value=mock_roi),
        ):
            result = runner.invoke(cli, ["publish", "results", "2026-03-01", "--dry-run"])
            assert result.exit_code == 0
            assert "的中レポート" in result.output

    def test_publish_results_no_results(self, runner: CliRunner) -> None:
        """When fetch_results returns empty, show error."""
        mock_resp = MagicMock()
        mock_resp.results = []

        with patch("boatrace_ai.cli.fetch_results", new_callable=AsyncMock, return_value=mock_resp):
            result = runner.invoke(cli, ["publish", "results", "2026-03-01", "--dry-run"])
            assert result.exit_code == 0
            assert "見つかりません" in result.output

    def test_publish_results_no_predictions(self, runner: CliRunner, results_json: dict) -> None:
        """When no predictions exist for the date, show error."""
        results_resp = ResultsResponse.model_validate(results_json)

        with (
            patch("boatrace_ai.cli.fetch_results", new_callable=AsyncMock, return_value=results_resp),
            patch("boatrace_ai.cli.save_result"),
            patch("boatrace_ai.cli.check_accuracy"),
            patch("boatrace_ai.cli.get_accuracy_for_date", return_value=[]),
            patch("boatrace_ai.cli.get_stats", return_value={"total_races": 0, "hit_1st": 0, "hit_1st_rate": 0.0, "hit_trifecta": 0, "hit_trifecta_rate": 0.0}),
        ):
            result = runner.invoke(cli, ["publish", "results", "2026-03-01", "--dry-run"])
            assert result.exit_code == 0
            assert "予測データが見つかりません" in result.output

    def test_publish_results_fetch_error(self, runner: CliRunner) -> None:
        """When fetch_results fails, show error."""
        with patch("boatrace_ai.cli.fetch_results", new_callable=AsyncMock, side_effect=Exception("Network")):
            result = runner.invoke(cli, ["publish", "results", "2026-03-01"])
            assert result.exit_code == 0
            assert "エラー" in result.output
