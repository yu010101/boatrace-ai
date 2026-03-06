"""X (Twitter) API client wrapper using tweepy.

Lazy-loads tweepy to keep it optional. Uses tweet_log DB table
for deduplication and audit trail.
"""

from __future__ import annotations

import logging

from boatrace_ai import config
from boatrace_ai.storage.database import get_tweet_log, save_tweet_log

log = logging.getLogger(__name__)


def _check_tweepy() -> None:
    """Raise ImportError with a helpful message if tweepy is not installed."""
    try:
        import tweepy  # noqa: F401
    except ImportError:
        raise ImportError(
            "X連携には tweepy が必要です。\n"
            "pip install 'boatrace-ai[social]' でインストールしてください。"
        )


def _get_client():
    """Create and return a tweepy Client instance."""
    import tweepy

    config.validate_twitter()

    return tweepy.Client(
        consumer_key=config.TWITTER_API_KEY,
        consumer_secret=config.TWITTER_API_SECRET,
        access_token=config.TWITTER_ACCESS_TOKEN,
        access_token_secret=config.TWITTER_ACCESS_SECRET,
    )


def post_tweet(
    tweet_text: str,
    tweet_type: str,
    race_date: str,
    stadium_number: int | None = None,
    race_number: int | None = None,
    dry_run: bool = False,
) -> str | None:
    """Post a tweet and log it.

    Args:
        tweet_text: The tweet content (max 280 chars)
        tweet_type: 'morning', 'hit', or 'daily'
        race_date: Date string for logging
        dry_run: If True, skip actual posting

    Returns:
        tweet_id if posted, None if dry_run or already posted.
    """
    # Check for duplicate
    existing = get_tweet_log(race_date, tweet_type)
    for entry in existing:
        if entry.get("stadium_number") == stadium_number and entry.get("race_number") == race_number:
            log.info("Tweet already posted: %s %s stadium=%s race=%s",
                     tweet_type, race_date, stadium_number, race_number)
            return None

    if dry_run:
        log.info("[DRY-RUN] Would tweet: %s", tweet_text)
        save_tweet_log(
            tweet_type=tweet_type,
            race_date=race_date,
            tweet_text=f"[DRY-RUN] {tweet_text}",
            stadium_number=stadium_number,
            race_number=race_number,
        )
        return None

    _check_tweepy()
    client = _get_client()

    response = client.create_tweet(text=tweet_text)
    tweet_id = str(response.data["id"])

    save_tweet_log(
        tweet_type=tweet_type,
        race_date=race_date,
        tweet_text=tweet_text,
        tweet_id=tweet_id,
        stadium_number=stadium_number,
        race_number=race_number,
    )

    log.info("Tweet posted: %s (id=%s)", tweet_type, tweet_id)
    return tweet_id


def reply_to_tweet(
    tweet_id: str,
    text: str,
    dry_run: bool = False,
) -> str | None:
    """Post a reply to an existing tweet.

    Returns:
        reply_tweet_id if posted, None if dry_run.
    """
    if dry_run:
        log.info("[DRY-RUN] Would reply to %s: %s", tweet_id, text)
        return None

    _check_tweepy()
    client = _get_client()

    try:
        response = client.create_tweet(text=text, in_reply_to_tweet_id=tweet_id)
        reply_id = str(response.data["id"])
        log.info("Reply posted to %s (reply_id=%s)", tweet_id, reply_id)
        return reply_id
    except Exception as e:
        log.warning("Failed to reply to tweet %s: %s", tweet_id, e)
        return None


def post_tweet_with_link_reply(
    main_text: str,
    link_text: str,
    tweet_type: str,
    race_date: str,
    stadium_number: int | None = None,
    race_number: int | None = None,
    dry_run: bool = False,
) -> tuple[str | None, str | None]:
    """Post main tweet then self-reply with link (avoids external link penalty).

    Returns:
        (main_tweet_id, reply_tweet_id) tuple.
    """
    main_id = post_tweet(
        main_text,
        tweet_type=tweet_type,
        race_date=race_date,
        stadium_number=stadium_number,
        race_number=race_number,
        dry_run=dry_run,
    )
    if main_id:
        reply_id = reply_to_tweet(main_id, link_text, dry_run=dry_run)
        return main_id, reply_id
    return None, None


def quote_repost(
    tweet_id: str,
    text: str,
    race_date: str,
    dry_run: bool = False,
) -> str | None:
    """Post a quote repost of an existing tweet.

    Returns:
        our_tweet_id if posted, None if dry_run.
    """
    if dry_run:
        log.info("[DRY-RUN] Would quote tweet %s: %s", tweet_id, text)
        return None

    _check_tweepy()
    client = _get_client()

    try:
        response = client.create_tweet(text=text, quote_tweet_id=tweet_id)
        our_id = str(response.data["id"])
        log.info("Quote repost of %s posted (id=%s)", tweet_id, our_id)
        return our_id
    except Exception as e:
        log.warning("Failed to quote tweet %s: %s", tweet_id, e)
        return None


def like_tweet(tweet_id: str, dry_run: bool = False) -> bool:
    """Like a tweet.

    Returns:
        True if liked successfully, False otherwise.
    """
    if dry_run:
        log.info("[DRY-RUN] Would like tweet %s", tweet_id)
        return True

    _check_tweepy()
    client = _get_client()

    try:
        client.like(tweet_id)
        log.info("Liked tweet %s", tweet_id)
        return True
    except Exception as e:
        log.warning("Failed to like tweet %s: %s", tweet_id, e)
        return False


def search_recent_tweets(query: str, max_results: int = 10) -> list[dict]:
    """Search recent tweets.

    Returns:
        List of dicts with id, text, author_id, created_at.
    """
    _check_tweepy()
    client = _get_client()

    try:
        response = client.search_recent_tweets(
            query=query,
            max_results=max(10, min(max_results, 100)),
            tweet_fields=["created_at", "author_id", "public_metrics"],
        )
        if not response.data:
            return []
        return [
            {
                "id": str(t.id),
                "text": t.text,
                "author_id": str(t.author_id),
                "created_at": str(t.created_at) if t.created_at else "",
                "metrics": t.public_metrics or {},
            }
            for t in response.data
        ]
    except Exception as e:
        log.warning("Tweet search failed for '%s': %s", query, e)
        return []


def get_user_recent_tweets(username: str, max_results: int = 5) -> list[dict]:
    """Get recent tweets from a specific user.

    Returns:
        List of dicts with id, text, created_at.
    """
    _check_tweepy()
    client = _get_client()

    try:
        user = client.get_user(username=username)
        if not user.data:
            log.warning("User not found: %s", username)
            return []

        response = client.get_users_tweets(
            id=user.data.id,
            max_results=max(5, min(max_results, 100)),
            tweet_fields=["created_at", "public_metrics"],
        )
        if not response.data:
            return []
        return [
            {
                "id": str(t.id),
                "text": t.text,
                "created_at": str(t.created_at) if t.created_at else "",
                "metrics": t.public_metrics or {},
            }
            for t in response.data
        ]
    except Exception as e:
        log.warning("Failed to get tweets for @%s: %s", username, e)
        return []
