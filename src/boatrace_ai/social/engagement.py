"""X engagement strategy: quote repost + reply chain for initial growth.

Based on X's public algorithm (twitter/the-algorithm, xAI/x-algorithm):

Engagement weights (vs like = 0.5x baseline):
  - Reply chain (相手が返信) = 75x  ← 最重要。会話を作れ
  - Reply                    = 13.5x
  - Quote repost             ≈ 25x  (新ツイート + リポスト信号)
  - Repost                   = 1x
  - Like                     = 0.5x
  - Negative (block/mute)    = -74x  ← 絶対に回避

Growth strategy for new accounts:
  1. 引用RTで大手に通知 → リポスト返しで露出獲得
  2. リプライで会話チェーン → 75x重み
  3. Real Graph構築 → 毎日の継続エンゲージで相互認知
  4. 投稿後30分が勝負 → 早期エンゲージがリーチを決定
"""

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
# Research: 10-20 quotes/day is safe for new accounts.
# Start at 10, aggressive but below spam threshold.

MAX_QUOTES_PER_DAY = 10
MAX_REPLIES_PER_DAY = 30
MAX_LIKES_PER_DAY = 50
MAX_QUOTES_PER_HANDLE_PER_DAY = 3

# ── Quote templates ──────────────────────────────────────
# Strategy: 相手に"価値"を提供して、リポスト返し・返信を誘発する
# - データや数字を出す（AIならではの差別化）
# - 質問で返信を誘う（返信チェーン = 75x重み）
# - 相手を持ち上げる（リポスト返しの動機）

QUOTE_TEMPLATES_HIT = [
    # 相手が的中した時 → 称賛 + データ補足 + 質問（返信誘発）
    "見事な的中! 水理AIのモデルでもこのレースは確信度上位でした。データが一致すると堅いですね\n\nちなみにモーター評価と展示タイムどちらを重視されてますか？",
    "的中おめでとうございます。水理AIの分析でも1着候補一致してました\n\nこの読み、モーター重視ですか？ それとも選手の相性？ 気になります",
    "お見事! このレース、水理AIでも推奨度Sランクでした。やっぱりデータが揃うと堅い\n\n同じレース注目してた方いると嬉しいですね",
]

QUOTE_TEMPLATES_PREDICTION = [
    # 相手が予想を出した時 → 同意 + AI視点の補足データ
    "水理AIでも同レース注目。モデルの1着確率が突出してるので堅い一戦に見えます\n\nデータで裏付けが取れる予想は信頼できますね #競艇予想",
    "同意です。水理AIの特徴量分析でもモーター2連率と展示タイムが揃ってるレース\n\nこういう根拠のある予想、参考になります #ボートレース",
    "なるほど、この視点は面白い。水理AIだとモーター評価で別角度から見てますが、結論は同じでした\n\nやっぱり強い予想家の読みとAIが一致すると自信持てます",
]

QUOTE_TEMPLATES_INFO = [
    # 公式やレース情報系 → データ追加で価値提供
    "水理AIのデータベースでもこのレース注目してます。ML予測で推奨度ランク付きの全場分析を毎朝配信中\n\n#ボートレース #競艇AI予測",
    "このレース、水理AIの分析では注目度が高いです。データで見ると面白い一戦になりそう\n\n#競艇予想 #ボートレース",
]

# All quote templates combined for random selection
QUOTE_TEMPLATES = QUOTE_TEMPLATES_HIT + QUOTE_TEMPLATES_PREDICTION + QUOTE_TEMPLATES_INFO

REPLY_TEMPLATES_CONVERSATION = [
    # 返信チェーン狙い: 質問で相手に返信させる（75x重み）
    "注目レースですね! モーターデータ的にも面白そうです。ちなみに展示タイムはチェックされましたか？",
    "さすがの読みですね。水理AIでも同じ結論でした。このレース、風の影響どう見てますか？",
    "データ分析でも堅い一戦に見えます。3連単の買い目、何点くらいで絞ってますか？",
    "同じく注目してました! インコースの信頼度が高いレースですよね。1号艇のモーターどう評価されてますか？",
]

REPLY_TEMPLATES_PRAISE = [
    # 称賛系: 相手を持ち上げてリポスト返しを狙う
    "的中おめでとうございます! いつも精度高くて参考にしてます",
    "さすがです。このレースは難しかったのに見事な読みですね",
    "いつも勉強になります。データ分析やってる身として、この精度は本当にすごい",
]

REPLY_TEMPLATES = REPLY_TEMPLATES_CONVERSATION + REPLY_TEMPLATES_PRAISE

# ── Keyword filters ──────────────────────────────────────

BOATRACE_KEYWORDS = [
    "競艇", "ボートレース", "予想", "的中", "舟券",
    "3連単", "2連単", "単勝", "推奨", "ランク",
    "SG", "G1", "レース", "モーター", "展示",
]

HIT_KEYWORDS = ["的中", "当たり", "プラス", "回収", "払戻"]
PREDICTION_KEYWORDS = ["予想", "予測", "推奨", "注目", "狙い", "本命"]


def _is_boatrace_related(text: str) -> bool:
    """Check if tweet text is boatrace-related."""
    return any(kw in text for kw in BOATRACE_KEYWORDS)


def _classify_tweet(text: str) -> str:
    """Classify tweet as 'hit', 'prediction', or 'info'."""
    if any(kw in text for kw in HIT_KEYWORDS):
        return "hit"
    if any(kw in text for kw in PREDICTION_KEYWORDS):
        return "prediction"
    return "info"


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


def pick_quote_template(tweet_text: str = "") -> str:
    """Pick a quote template matched to the tweet content."""
    category = _classify_tweet(tweet_text)
    if category == "hit":
        return random.choice(QUOTE_TEMPLATES_HIT)
    elif category == "prediction":
        return random.choice(QUOTE_TEMPLATES_PREDICTION)
    return random.choice(QUOTE_TEMPLATES_INFO)


def pick_reply_template(tweet_text: str = "") -> str:
    """Pick a reply template. Prioritize conversation starters (75x weight)."""
    # 70% conversation (question-based), 30% praise
    if random.random() < 0.7:
        return random.choice(REPLY_TEMPLATES_CONVERSATION)
    return random.choice(REPLY_TEMPLATES_PRAISE)


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

    Strategy by timing:
      morning: 全ターゲットに引用RT攻勢（予想ツイートへの引用RT）
      evening: 全ターゲットに引用RT + 的中報告への称賛リプライ

    Args:
        timing: 'morning' or 'evening'
        dry_run: If True, don't actually post

    Returns:
        Summary dict with counts of actions taken.
    """
    from boatrace_ai.social.twitter import like_tweet, quote_repost, reply_to_tweet

    race_date = date.today().isoformat()
    summary = {"quotes": 0, "replies": 0, "likes": 0, "skipped": 0}

    scan_results = scan_targets()
    if not scan_results:
        log.info("No boatrace-related tweets found from targets")
        return summary

    for target_data in scan_results:
        handle = target_data["handle"]
        tweets = target_data["tweets"]

        if not tweets:
            continue

        # Engage with multiple tweets per target (not just the best one)
        for tweet in tweets:
            # Like every relevant tweet (builds Real Graph)
            if can_like(race_date):
                liked = like_tweet(tweet["id"], dry_run=dry_run)
                if liked or dry_run:
                    if liked and not dry_run:
                        save_engagement_log(
                            "like", handle, race_date,
                            target_tweet_id=tweet["id"],
                        )
                    summary["likes"] += 1

        # Pick the best tweet for quote RT (highest engagement potential)
        best_tweet = max(
            tweets,
            key=lambda t: t.get("metrics", {}).get("like_count", 0)
            + t.get("metrics", {}).get("retweet_count", 0) * 2,
        )

        # Quote RT: primary growth lever
        if can_quote(race_date, handle):
            text = pick_quote_template(best_tweet["text"])
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

        # Reply: aim for conversation chain (75x weight)
        if can_reply(race_date):
            # Reply to a different tweet than the one we quoted
            reply_tweet = tweets[1] if len(tweets) > 1 else best_tweet
            text = pick_reply_template(reply_tweet["text"])
            reply_id = reply_to_tweet(
                reply_tweet["id"], text, dry_run=dry_run,
            )
            if reply_id or dry_run:
                if not dry_run:
                    save_engagement_log(
                        "reply", handle, race_date,
                        target_tweet_id=reply_tweet["id"],
                        our_tweet_id=reply_id,
                        tweet_text=text,
                    )
                summary["replies"] += 1

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
