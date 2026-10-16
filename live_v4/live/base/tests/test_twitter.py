"""Tests for social/twitter.py and social/templates.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from boatrace_ai.social.templates import (
    MAX_TWEET_LENGTH,
    build_daily_tweet,
    build_hit_tweet,
    build_morning_tweet,
)
from boatrace_ai.storage.database import init_db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    with patch("boatrace_ai.storage.database.config") as mock_config:
        mock_config.DB_PATH = db_path
        init_db()
        yield mock_config


# ── Templates ─────────────────────────────────────────────


def test_morning_tweet_with_s_rank() -> None:
    s_races = [
        {"stadium_number": 4, "race_number": 3, "grade": "S"},
        {"stadium_number": 12, "race_number": 7, "grade": "S"},
    ]
    tweet = build_morning_tweet("2026-03-02", s_races)
    assert "AI予測" in tweet
    assert "2026-03-02" in tweet
    assert "推奨度S" in tweet
    assert len(tweet) <= MAX_TWEET_LENGTH


def test_morning_tweet_no_s_rank() -> None:
    tweet = build_morning_tweet("2026-03-02", [])
    assert "Sランク該当なし" in tweet


def test_morning_tweet_with_url() -> None:
    tweet = build_morning_tweet("2026-03-02", [], note_url="https://note.com/test")
    assert "https://note.com/test" not in tweet  # URL no longer embedded (link penalty)
    assert "プロフリンクから" in tweet


def test_hit_tweet() -> None:
    tweet = build_hit_tweet(
        "2026-03-02",
        stadium_number=4,
        race_number=3,
        bet_type="3連単",
        combination="1-3-2",
        payout=15000,
        grade="S",
    )
    assert "的中" in tweet
    assert "3連単" in tweet
    assert "1-3-2" in tweet
    assert "¥15,000" in tweet
    assert "推奨度S" in tweet
    assert len(tweet) <= MAX_TWEET_LENGTH


def test_hit_tweet_without_grade() -> None:
    tweet = build_hit_tweet(
        "2026-03-02",
        stadium_number=4,
        race_number=3,
        bet_type="単勝",
        combination="1",
        payout=2000,
    )
    assert "推奨度" not in tweet
    assert "単勝" in tweet


def test_daily_tweet_profit() -> None:
    tweet = build_daily_tweet(
        "2026-03-02",
        total_races=12,
        hit_count=4,
        roi=1.32,
    )
    assert "12R中4R的中" in tweet
    assert "132%" in tweet
    assert "プラス収支" in tweet
    assert len(tweet) <= MAX_TWEET_LENGTH


def test_daily_tweet_loss() -> None:
    tweet = build_daily_tweet(
        "2026-03-02",
        total_races=10,
        hit_count=1,
        roi=0.5,
    )
    assert "50%" in tweet
    assert "プラス収支" not in tweet


def test_daily_tweet_with_url() -> None:
    tweet = build_daily_tweet(
        "2026-03-02",
        total_races=10,
        hit_count=3,
        roi=1.2,
        note_url="https://note.com/report",
    )
    assert "https://note.com/report" not in tweet  # URL no longer embedded (link penalty)
    assert "プロフリンクから" in tweet


def test_tweet_truncation() -> None:
    """Very long content should be truncated to MAX_TWEET_LENGTH."""
    # Create many S-rank races to make a long tweet
    s_races = [
        {"stadium_number": i, "race_number": j, "grade": "S"}
        for i in range(1, 25) for j in range(1, 13)
    ]
    tweet = build_morning_tweet("2026-03-02", s_races, note_url="https://note.com/very_long_url_that_goes_on_and_on")
    assert len(tweet) <= MAX_TWEET_LENGTH


# ── Twitter client ────────────────────────────────────────


def test_post_tweet_dry_run() -> None:
    """Dry-run should not call tweepy, just log."""
    from boatrace_ai.social.twitter import post_tweet

    result = post_tweet(
        tweet_text="テスト",
        tweet_type="morning",
        race_date="2026-03-02",
        dry_run=True,
    )
    assert result is None


def test_post_tweet_duplicate_check() -> None:
    """Duplicate tweet (same type+date+stadium+race) should be skipped."""
    from boatrace_ai.social.twitter import post_tweet
    from boatrace_ai.storage.database import save_tweet_log

    # Pre-populate a tweet log
    save_tweet_log(
        tweet_type="hit",
        race_date="2026-03-02",
        tweet_text="previous tweet",
        stadium_number=4,
        race_number=3,
    )

    # Try posting same type+date+stadium+race
    result = post_tweet(
        tweet_text="新しいツイート",
        tweet_type="hit",
        race_date="2026-03-02",
        stadium_number=4,
        race_number=3,
        dry_run=True,
    )
    assert result is None


# ── Config validation ─────────────────────────────────────


def test_validate_twitter_missing_keys() -> None:
    """Missing API keys should raise ValueError."""
    with patch("boatrace_ai.config.TWITTER_API_KEY", ""):
        with pytest.raises(ValueError, match="TWITTER_API_KEY"):
            from boatrace_ai.config import validate_twitter
            validate_twitter()
