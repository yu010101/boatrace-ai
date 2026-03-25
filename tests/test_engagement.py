"""Tests for social/engagement.py and engagement-related features."""

from __future__ import annotations

import time
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


def test_rate_limits_aggressive():
    """Rate limits should be aggressive enough for initial growth."""
    from boatrace_ai.social.engagement import (
        MAX_LIKES_PER_DAY,
        MAX_QUOTES_PER_DAY,
        MAX_QUOTES_PER_HANDLE_PER_DAY,
        MAX_REPLIES_PER_DAY,
    )

    assert MAX_QUOTES_PER_DAY >= 10  # Research: 10-20 is safe
    assert MAX_REPLIES_PER_DAY >= 20
    assert MAX_LIKES_PER_DAY >= 30
    assert MAX_QUOTES_PER_HANDLE_PER_DAY >= 2  # Multiple quotes per target OK


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
    from boatrace_ai.social.engagement import MAX_QUOTES_PER_HANDLE_PER_DAY, can_quote
    from boatrace_ai.storage.database import save_engagement_log

    for i in range(MAX_QUOTES_PER_HANDLE_PER_DAY):
        save_engagement_log("quote", "ichimaru10kun", "2026-03-06")

    assert can_quote("2026-03-06", "ichimaru10kun") is False
    assert can_quote("2026-03-06", "kataru4649") is True


def test_can_reply_under_limit():
    from boatrace_ai.social.engagement import can_reply

    assert can_reply("2026-03-06") is True


def test_can_like_under_limit():
    from boatrace_ai.social.engagement import can_like

    assert can_like("2026-03-06") is True


# ── Tweet classification ─────────────────────────────────


def test_classify_tweet():
    from boatrace_ai.social.engagement import _classify_tweet

    assert _classify_tweet("3連単的中! 払戻12,000円") == "hit"
    assert _classify_tweet("明日の注目レース予想") == "prediction"
    assert _classify_tweet("桐生のレース結果") == "info"


# ── Templates ────────────────────────────────────────────


def test_pick_quote_template_matches_content():
    """Template should be picked from the correct category (with humanization)."""
    from boatrace_ai.social.engagement import (
        QUOTE_TEMPLATES_HIT,
        QUOTE_TEMPLATES_INFO,
        QUOTE_TEMPLATES_PREDICTION,
        pick_quote_template,
    )

    # Check that the base template (before humanization) is from the right category
    hit_tmpl = pick_quote_template("3連単的中!")
    assert any(base in hit_tmpl for base in QUOTE_TEMPLATES_HIT)

    pred_tmpl = pick_quote_template("明日の予想レース")
    assert any(base in pred_tmpl for base in QUOTE_TEMPLATES_PREDICTION)

    info_tmpl = pick_quote_template("今日のレース情報")
    assert any(base in info_tmpl for base in QUOTE_TEMPLATES_INFO)


def test_quote_templates_have_value():
    """Quote templates should provide data/questions to trigger repost-back."""
    from boatrace_ai.social.engagement import QUOTE_TEMPLATES

    for tmpl in QUOTE_TEMPLATES:
        has_brand = "水理AI" in tmpl
        has_data = any(w in tmpl for w in ["データ", "分析", "モデル", "確率", "特徴量", "推奨度", "ML", "AI"])
        assert has_brand or has_data, f"Template lacks value-add: {tmpl[:50]}"


def test_reply_templates_have_questions():
    """Conversation templates should have questions to trigger reply chains (75x)."""
    from boatrace_ai.social.engagement import REPLY_TEMPLATES_CONVERSATION

    for tmpl in REPLY_TEMPLATES_CONVERSATION:
        assert "？" in tmpl or "?" in tmpl, f"Conversation template lacks question: {tmpl[:50]}"


def test_humanize_text_varies():
    """_humanize_text should sometimes produce different output."""
    from boatrace_ai.social.engagement import _humanize_text

    base = "テスト文章です"
    results = set()
    for _ in range(50):
        results.add(_humanize_text(base))
    # Should produce at least 2 different variations over 50 runs
    assert len(results) >= 2, "humanize_text should add variation"


def test_human_delay_skipped_on_dry_run():
    """_human_delay should not sleep during dry_run."""
    from boatrace_ai.social.engagement import _human_delay

    start = time.time()
    _human_delay(dry_run=True)
    elapsed = time.time() - start
    assert elapsed < 0.1


def test_pick_reply_template():
    from boatrace_ai.social.engagement import REPLY_TEMPLATES, pick_reply_template

    template = pick_reply_template()
    # _humanize_text modifies the template, so check it's a non-empty string
    assert isinstance(template, str)
    assert len(template) > 0


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
    assert main_id is None
    assert reply_id is None


# ── execute_engagement ───────────────────────────────────


def _make_mock_tweets(n=2):
    return [
        {"id": str(100 + i), "text": "競艇予想です", "created_at": "", "metrics": {"like_count": 5 - i, "retweet_count": 1}}
        for i in range(n)
    ]


def test_execute_engagement_dry_run_no_db_writes():
    """dry_run=True should NOT save engagement logs to DB."""
    from boatrace_ai.social.engagement import execute_engagement
    from boatrace_ai.storage.database import get_engagement_count

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.engagement.TARGET_ENGAGE_PROB", 1.0), \
         patch("boatrace_ai.social.engagement.LIKE_PROB", 1.0), \
         patch("boatrace_ai.social.engagement.BOTH_QUOTE_AND_REPLY_PROB", 1.0), \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=True), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": _make_mock_tweets()},
        ]

        summary = execute_engagement(timing="morning", dry_run=True)

    assert summary["likes"] + summary["quotes"] + summary["replies"] > 0
    today = date.today().isoformat()
    assert get_engagement_count(today, "like") == 0
    assert get_engagement_count(today, "quote") == 0
    assert get_engagement_count(today, "reply") == 0


def test_execute_engagement_randomness_skips_some():
    """With randomness, some targets/likes should be skipped."""
    from boatrace_ai.social.engagement import execute_engagement

    # Run many times and verify we get different results
    results = []
    for _ in range(10):
        with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
             patch("boatrace_ai.social.twitter.like_tweet", return_value=True), \
             patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
             patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
            mock_scan.return_value = [
                {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": _make_mock_tweets(3)},
                {"handle": "kataru4649", "name": "カタル", "priority": "S", "tweets": _make_mock_tweets(3)},
                {"handle": "BoatMvhstPq", "name": "マーズ", "priority": "A", "tweets": _make_mock_tweets(3)},
            ]
            summary = execute_engagement(timing="morning", dry_run=True)
            results.append(summary["likes"])

    # With randomness, not every run should produce the same like count
    unique_counts = set(results)
    assert len(unique_counts) >= 2, f"Results should vary but got {unique_counts}"


def test_execute_engagement_with_full_engagement():
    """With all probabilities at 1.0, should engage with everything."""
    from boatrace_ai.social.engagement import execute_engagement

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.engagement.TARGET_ENGAGE_PROB", 1.0), \
         patch("boatrace_ai.social.engagement.LIKE_PROB", 1.0), \
         patch("boatrace_ai.social.engagement.BOTH_QUOTE_AND_REPLY_PROB", 1.0), \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=True), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": _make_mock_tweets(2)},
        ]

        summary = execute_engagement(timing="morning", dry_run=True)

    assert summary["likes"] == 2  # All tweets liked
    assert summary["quotes"] == 1
    assert summary["replies"] == 1


def test_execute_engagement_api_failure_no_log():
    """Failed API calls should not save engagement logs."""
    from boatrace_ai.social.engagement import execute_engagement
    from boatrace_ai.storage.database import get_engagement_count

    with patch("boatrace_ai.social.engagement.scan_targets") as mock_scan, \
         patch("boatrace_ai.social.engagement.TARGET_ENGAGE_PROB", 1.0), \
         patch("boatrace_ai.social.engagement.LIKE_PROB", 1.0), \
         patch("boatrace_ai.social.engagement.BOTH_QUOTE_AND_REPLY_PROB", 1.0), \
         patch("boatrace_ai.social.twitter.like_tweet", return_value=False), \
         patch("boatrace_ai.social.twitter.quote_repost", return_value=None), \
         patch("boatrace_ai.social.twitter.reply_to_tweet", return_value=None):
        mock_scan.return_value = [
            {"handle": "ichimaru10kun", "name": "いちまる", "priority": "S", "tweets": _make_mock_tweets()},
        ]

        execute_engagement(timing="evening", dry_run=False)

    today = date.today().isoformat()
    assert get_engagement_count(today, "like") == 0
    assert get_engagement_count(today, "quote") == 0
