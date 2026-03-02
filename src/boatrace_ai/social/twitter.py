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
