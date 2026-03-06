"""Tests for social/engagement.py and engagement-related features."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from boatrace_ai.storage.database import init_db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    with patch("boatrace_ai.storage.database.config") as mock_config:
        mock_config.DB_PATH = db_path
        init_db()
        yield mock_config


# ── Target accounts ──────────────────────────────────────


def test_target_accounts_structure():
    from boatrace_ai.social.engagement import TARGET_ACCOUNTS

    assert len(TARGET_ACCOUNTS) >= 7
    for t in TARGET_ACCOUNTS:
        assert "handle" in t
        assert "name" in t
        assert "priority" in t
        assert t["priority"] in ("S", "A", "B")


def test_get_sorted_targets():
    from boatrace_ai.social.engagement import get_sorted_targets

    targets = get_sorted_targets()
    priorities = [t["priority"] for t in targets]
    # S should come before A, A before B
    s_indices = [i for i, p in enumerate(priorities) if p == "S"]
    a_indices = [i for i, p in enumerate(priorities) if p == "A"]
    b_indices = [i for i, p in enumerate(priorities) if p == "B"]
    if s_indices and a_indices:
        assert max(s_indices) < min(a_indices)
    if a_indices and b_indices:
        assert max(a_indices) < min(b_indices)


def test_get_sorted_targets_filter():
    from boatrace_ai.social.engagement import get_sorted_targets

    s_only = get_sorted_targets("S")
    assert all(t["priority"] == "S" for t in s_only)
    assert len(s_only) >= 3


# ── Rate limiting ────────────────────────────────────────


def test_can_quote_under_limit():
    from boatrace_ai.social.engagement import can_quote

    assert can_quote("2026-03-06") is True


def test_can_quote_at_limit():
    from boatrace_ai.social.engagement import MAX_QUOTES_PER_DAY, can_quote
    from boatrace_ai.storage.database import save_engagement_log

    for i in range(MAX_QUOTES_PER_DAY):
        save_engagement_log("quote", f"user{i}", "2026-03-06")

    assert can_quote("2026-03-06") is False


def test_can_quote_per_handle_limit():
    from boatrace_ai.social.engagement import can_quote
    from boatrace_ai.storage.database import save_engagement_log

    save_engagement_log("quote", "ichimaru10kun", "2026-03-06")
    assert can_quote("2026-03-06", "ichimaru10kun") is False
    assert can_quote("2026-03-06", "kataru4649") is True


def test_can_reply_under_limit():
    from boatrace_ai.social.engagement import can_reply

    assert can_reply("2026-03-06") is True


def test_can_like_under_limit():
    from boatrace_ai.social.engagement import can_like

    assert can_like("2026-03-06") is True


# ── Templates ────────────────────────────────────────────


def test_pick_quote_template():
    from boatrace_ai.social.engagement import QUOTE_TEMPLATES, pick_quote_template

    template = pick_quote_template()
    assert template in QUOTE_TEMPLATES


def test_pick_reply_template():
    from boatrace_ai.social.engagement import REPLY_TEMPLATES, pick_reply_template

    template = pick_reply_template()
    assert template in REPLY_TEMPLATES


# ── Keyword filter ───────────────────────────────────────


def test_is_boatrace_related():
    from boatrace_ai.social.engagement import _is_boatrace_related

    assert _is_boatrace_related("今日の競艇予想です") is True
    assert _is_boatrace_related("ボートレース楽しい") is True
    assert _is_boatrace_related("3連単的中!") is True
    assert _is_boatrace_related("今日のランチは美味しかった") is False


# ── Engagement stats ─────────────────────────────────────


def test_get_engagement_stats():
    from boatrace_ai.social.engagement import get_engagement_stats
    from boatrace_ai.storage.database import save_engagement_log

    save_engagement_log("quote", "test_user", "2026-03-06")
    save_engagement_log("reply", "test_user", "2026-03-06")
    save_engagement_log("like", "test_user", "2026-03-06")
    save_engagement_log("like", "test_user2", "2026-03-06")

    stats = get_engagement_stats("2026-03-06")
    assert stats["quotes"] == 1
    assert stats["replies"] == 1
    assert stats["likes"] == 2
    assert "limits" in stats


# ── Database CRUD ────────────────────────────────────────


def test_engagement_log_crud():
    from boatrace_ai.storage.database import (
        get_engagement_count,
        get_engagement_log,
        save_engagement_log,
    )

    save_engagement_log(
        "quote", "ichimaru10kun", "2026-03-06",
        target_tweet_id="123", our_tweet_id="456", tweet_text="test",
    )
    save_engagement_log(
        "reply", "kataru4649", "2026-03-06",
        target_tweet_id="789", our_tweet_id="012",
    )

    assert get_engagement_count("2026-03-06", "quote") == 1
    assert get_engagement_count("2026-03-06", "reply") == 1
    assert get_engagement_count("2026-03-06", "like") == 0

    log = get_engagement_log("2026-03-06")
    assert len(log) == 2
    assert log[0]["target_handle"] == "ichimaru10kun"
    assert log[0]["tweet_text"] == "test"


# ── Template link penalty fix ────────────────────────────


def test_morning_tweet_no_direct_url():
    from boatrace_ai.social.templates import build_morning_tweet

    tweet = build_morning_tweet("2026-03-06", [], note_url="https://note.com/suiri_ai")
    assert "https://note.com" not in tweet
    assert "プロフリンクから" in tweet


def test_daily_tweet_no_direct_url():
    from boatrace_ai.social.templates import build_daily_tweet

    tweet = build_daily_tweet("2026-03-06", 10, 3, 1.2, note_url="https://note.com/report")
    assert "https://note.com" not in tweet
    assert "プロフリンクから" in tweet


def test_midday_tweet_no_direct_url():
    from boatrace_ai.social.templates import build_midday_tweet

    tweet = build_midday_tweet("2026-03-06", 10, 3, 1, note_url="https://note.com/report")
    assert "https://note.com" not in tweet
    assert "プロフリンクから" in tweet


# ── Twitter API extensions ───────────────────────────────


def test_reply_to_tweet_dry_run():
    from boatrace_ai.social.twitter import reply_to_tweet

    result = reply_to_tweet("12345", "テスト返信", dry_run=True)
    assert result is None


def test_quote_repost_dry_run():
    from boatrace_ai.social.twitter import quote_repost

    result = quote_repost("12345", "テスト引用", "2026-03-06", dry_run=True)
    assert result is None


def test_like_tweet_dry_run():
    from boatrace_ai.social.twitter import like_tweet

    result = like_tweet("12345", dry_run=True)
    assert result is True


def test_post_tweet_with_link_reply_dry_run():
    from boatrace_ai.social.twitter import post_tweet_with_link_reply

    main_id, reply_id = post_tweet_with_link_reply(
        main_text="メインツイート",
        link_text="詳細: https://note.com/suiri_ai",
        tweet_type="morning",
        race_date="2026-03-06",
        dry_run=True,
    )
    # dry_run returns None for both
    assert main_id is None
    assert reply_id is None


# ── execute_engagement ───────────────────────────────────


def test_execute_engagement_dry_run_no_db_writes():
    """dry_run=True should NOT save engagement logs to DB."""
    from boatrace_ai.social.engagement import execute_engagement
    from boatrace_ai.storage.database import get_engagement_count

    mock_tweets = [
        {"id": "111", "text": "競艇予想です", "created_at": "", "metrics": {"like_count": 5, "retweet_count": 1}},
    ]

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=True), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": mock_tweets},
        ]

        summary = execute_engagement(timing="morning", dry_run=True)

    # Should count actions in summary
    assert summary["likes"] + summary["quotes"] + summary["replies"] > 0
    # But should NOT write to DB
    assert get_engagement_count("2026-03-06", "like") == 0
    assert get_engagement_count("2026-03-06", "quote") == 0
    assert get_engagement_count("2026-03-06", "reply") == 0


def test_execute_engagement_morning_filters_s_priority():
    """Morning timing should only engage with S-priority targets."""
    from boatrace_ai.social.engagement import execute_engagement

    mock_tweets = [
        {"id": "222", "text": "ボートレース予想", "created_at": "", "metrics": {"like_count": 3, "retweet_count": 0}},
    ]

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=True), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": mock_tweets},
            {"handle": "BoatMvhstPq", "name": "マーズ", "priority": "A", "tweets": mock_tweets},
            {"handle": "boat_race_k", "name": "要", "priority": "B", "tweets": mock_tweets},
        ]

        summary = execute_engagement(timing="morning", dry_run=True)

    # Morning: only S-priority → 1 target processed
    assert summary["likes"] == 1


def test_execute_engagement_evening_all_priorities():
    """Evening timing should engage with all priority targets."""
    from boatrace_ai.social.engagement import execute_engagement

    mock_tweets = [
        {"id": "333", "text": "競艇的中!", "created_at": "", "metrics": {"like_count": 1, "retweet_count": 0}},
    ]

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=True), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": mock_tweets},
            {"handle": "BoatMvhstPq", "name": "マーズ", "priority": "A", "tweets": mock_tweets},
            {"handle": "boat_race_k", "name": "要", "priority": "B", "tweets": mock_tweets},
        ]

        summary = execute_engagement(timing="evening", dry_run=True)

    # Evening: all priorities → 3 targets processed
    assert summary["likes"] == 3


def test_execute_engagement_api_failure_no_log():
    """Failed API calls should not save engagement logs."""
    from boatrace_ai.social.engagement import execute_engagement
    from boatrace_ai.storage.database import get_engagement_count

    mock_tweets = [
        {"id": "444", "text": "競艇予想", "created_at": "", "metrics": {"like_count": 0, "retweet_count": 0}},
    ]

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=False), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": mock_tweets},
        ]

        execute_engagement(timing="evening", dry_run=False)

    # API returned failure → no DB writes
    assert get_engagement_count(date.today().isoformat(), "like") == 0
    assert get_engagement_count(date.today().isoformat(), "quote") == 0
