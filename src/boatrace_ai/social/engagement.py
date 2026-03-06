"""X engagement strategy: quote repost + reply + like targeting."""

from __future__ import annotations

import logging
import random
from datetime import date

from boatrace_ai.storage.database import (
    get_engagement_count,
    get_engagement_count_for_handle,
    save_engagement_log,
)

log = logging.getLogger(__name__)

# ── Target accounts ──────────────────────────────────────

TARGET_ACCOUNTS = [
    {"handle": "ichimaru10kun", "name": "いちまる", "followers": 120000, "priority": "S"},
    {"handle": "kataru4649", "name": "カタル", "followers": 40000, "priority": "S"},
    {"handle": "AI_POSEIDON", "name": "ポセイドン", "followers": 10000, "priority": "S"},
    {"handle": "BoatMvhstPq", "name": "マーズ", "followers": 9877, "priority": "A"},
    {"handle": "yosouya_suwan", "name": "すわん", "followers": 5000, "priority": "A"},
    {"handle": "boat_race_k", "name": "要", "followers": 3000, "priority": "B"},
    {"handle": "boatrace_jp", "name": "ボートレース公式", "followers": 0, "priority": "A"},
]

PRIORITY_ORDER = {"S": 0, "A": 1, "B": 2}

# ── Rate limits (daily) ─────────────────────────────────

MAX_QUOTES_PER_DAY = 3
MAX_REPLIES_PER_DAY = 20
MAX_LIKES_PER_DAY = 30
MAX_QUOTES_PER_HANDLE_PER_DAY = 1

# ── Templates ────────────────────────────────────────────

QUOTE_TEMPLATES = [
    "水理AIでも同レース注目してました。データで見ても堅い一戦\n\n#競艇予想 #ボートレース",
    "面白い着眼点。水理AIの分析でも注目ポイントが重なります\n\n#ボートレース #競艇予想",
    "見事な的中! 同レース水理AIも分析してました\n\nお互い精度上げていきましょう #競艇",
    "これは同意。データ分析でも裏付けが取れるレースですね\n\n#競艇AI予測 #ボートレース",
]

REPLY_TEMPLATES = [
    "注目レースですね。モーターデータ的にも面白そうです",
    "的中おめでとうございます! 難しいレースでしたね",
    "同じく注目してました。データ分析でも堅い一戦に見えます",
    "いつも参考にしてます。本日も注目レース多いですね",
]

# ── Keyword filters ──────────────────────────────────────

BOATRACE_KEYWORDS = [
    "競艇", "ボートレース", "予想", "的中", "舟券",
    "3連単", "2連単", "単勝", "推奨", "ランク",
    "SG", "G1", "レース", "モーター", "展示",
]


def _is_boatrace_related(text: str) -> bool:
    """Check if tweet text is boatrace-related."""
    return any(kw in text for kw in BOATRACE_KEYWORDS)


def get_sorted_targets(priority_filter: str | None = None) -> list[dict]:
    """Get target accounts sorted by priority (S > A > B)."""
    targets = TARGET_ACCOUNTS
    if priority_filter:
        targets = [t for t in targets if t["priority"] == priority_filter]
    return sorted(targets, key=lambda t: PRIORITY_ORDER.get(t["priority"], 99))


def can_quote(race_date: str, target_handle: str | None = None) -> bool:
    """Check if we can still quote today."""
    total = get_engagement_count(race_date, "quote")
    if total >= MAX_QUOTES_PER_DAY:
        return False
    if target_handle:
        handle_count = get_engagement_count_for_handle(race_date, "quote", target_handle)
        if handle_count >= MAX_QUOTES_PER_HANDLE_PER_DAY:
            return False
    return True


def can_reply(race_date: str) -> bool:
    """Check if we can still reply today."""
    return get_engagement_count(race_date, "reply") < MAX_REPLIES_PER_DAY


def can_like(race_date: str) -> bool:
    """Check if we can still like today."""
    return get_engagement_count(race_date, "like") < MAX_LIKES_PER_DAY


def pick_quote_template() -> str:
    """Pick a random quote template."""
    return random.choice(QUOTE_TEMPLATES)


def pick_reply_template() -> str:
    """Pick a random reply template."""
    return random.choice(REPLY_TEMPLATES)


def scan_targets(
    target_handle: str | None = None,
    max_tweets_per_target: int = 5,
) -> list[dict]:
    """Scan target accounts for recent boatrace-related tweets.

    Returns list of {handle, name, priority, tweets: [{id, text, ...}]}.
    """
    from boatrace_ai.social.twitter import get_user_recent_tweets

    targets = get_sorted_targets()
    if target_handle:
        targets = [t for t in targets if t["handle"] == target_handle]

    results = []
    for target in targets:
        tweets = get_user_recent_tweets(target["handle"], max_results=max_tweets_per_target)
        relevant = [t for t in tweets if _is_boatrace_related(t["text"])]
        if relevant:
            results.append({
                "handle": target["handle"],
                "name": target["name"],
                "priority": target["priority"],
                "tweets": relevant,
            })
    return results


def execute_engagement(
    timing: str = "morning",
    dry_run: bool = False,
) -> dict:
    """Execute auto engagement routine.

    Args:
        timing: 'morning' or 'evening'
        dry_run: If True, don't actually post

    Returns:
        Summary dict with counts of actions taken.
    """
    from boatrace_ai.social.twitter import like_tweet, quote_repost, reply_to_tweet

    race_date = date.today().isoformat()
    summary = {"quotes": 0, "replies": 0, "likes": 0, "skipped": 0}

    # Morning: focus on S-priority targets with quote RTs for visibility
    # Evening: broader engagement with replies (react to results/hit reports)
    priority_filter = "S" if timing == "morning" else None

    scan_results = scan_targets()
    if not scan_results:
        log.info("No boatrace-related tweets found from targets")
        return summary

    # Filter by priority for morning
    if priority_filter:
        scan_results = [r for r in scan_results if r["priority"] == priority_filter]

    for target_data in scan_results:
        handle = target_data["handle"]
        tweets = target_data["tweets"]

        if not tweets:
            continue

        # Pick the most engaging tweet (highest metrics)
        best_tweet = max(
            tweets,
            key=lambda t: t.get("metrics", {}).get("like_count", 0)
            + t.get("metrics", {}).get("retweet_count", 0) * 2,
        )

        # Like (always try first - low cost)
        if can_like(race_date):
            liked = like_tweet(best_tweet["id"], dry_run=dry_run)
            if liked or dry_run:
                if liked and not dry_run:
                    save_engagement_log(
                        "like", handle, race_date,
                        target_tweet_id=best_tweet["id"],
                    )
                summary["likes"] += 1

        # Quote RT (high value, limited)
        if can_quote(race_date, handle):
            text = pick_quote_template()
            our_id = quote_repost(
                best_tweet["id"], text, race_date, dry_run=dry_run,
            )
            if our_id or dry_run:
                if not dry_run:
                    save_engagement_log(
                        "quote", handle, race_date,
                        target_tweet_id=best_tweet["id"],
                        our_tweet_id=our_id,
                        tweet_text=text,
                    )
                summary["quotes"] += 1

        # Reply (medium value, more allowed)
        elif can_reply(race_date):
            text = pick_reply_template()
            reply_id = reply_to_tweet(
                best_tweet["id"], text, dry_run=dry_run,
            )
            if reply_id or dry_run:
                if not dry_run:
                    save_engagement_log(
                        "reply", handle, race_date,
                        target_tweet_id=best_tweet["id"],
                        our_tweet_id=reply_id,
                        tweet_text=text,
                    )
                summary["replies"] += 1

        else:
            summary["skipped"] += 1

    return summary


def get_engagement_stats(race_date: str | None = None) -> dict:
    """Get engagement statistics for a date."""
    target_date = race_date or date.today().isoformat()
    return {
        "date": target_date,
        "quotes": get_engagement_count(target_date, "quote"),
        "replies": get_engagement_count(target_date, "reply"),
        "likes": get_engagement_count(target_date, "like"),
        "limits": {
            "max_quotes": MAX_QUOTES_PER_DAY,
            "max_replies": MAX_REPLIES_PER_DAY,
            "max_likes": MAX_LIKES_PER_DAY,
        },
    }
