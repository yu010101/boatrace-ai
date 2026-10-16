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
import time
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

MAX_QUOTES_PER_DAY = 10
MAX_REPLIES_PER_DAY = 30
MAX_LIKES_PER_DAY = 50
MAX_QUOTES_PER_HANDLE_PER_DAY = 3

# ── Humanization parameters ──────────────────────────────

# Probability of engaging with each target (humans skip some)
TARGET_ENGAGE_PROB = 0.75
# Probability of liking each individual tweet
LIKE_PROB = 0.7
# Probability of doing both quote+reply (vs just one)
BOTH_QUOTE_AND_REPLY_PROB = 0.5
# Action delay range in seconds (human-like pauses)
ACTION_DELAY_MIN = 2
ACTION_DELAY_MAX = 8

# ── Text variation ───────────────────────────────────────

_FILLERS = ["", "なるほど、", "おお、", "これは、"]
_TRAIL_VARIATIONS = [
    "", " 注目してます", " 楽しみです", " 気になりますね",
]
_EMOJI_POOL = ["", "", "", "", " ✨", " 🎯", " 🔥", " 💡", " 📊"]

# ── Quote templates ──────────────────────────────────────

QUOTE_TEMPLATES_HIT = [
    "見事な的中! 水理AIのモデルでもこのレースは確信度上位でした。データが一致すると堅いですね\n\nちなみにモーター評価と展示タイムどちらを重視されてますか？",
    "的中おめでとうございます。水理AIの分析でも1着候補一致してました\n\nこの読み、モーター重視ですか？ それとも選手の相性？ 気になります",
    "お見事! このレース、水理AIでも推奨度Sランクでした。やっぱりデータが揃うと堅い\n\n同じレース注目してた方いると嬉しいですね",
    "的中すごい。水理AIでもこのレースは信頼度高かったです\n\n展示の段階で見えてた感じですか？",
    "ナイス的中! 水理AIでもモデル確率高めのレースでした\n\nやっぱり堅いレースは人もAIも見解一致しますね",
]

QUOTE_TEMPLATES_PREDICTION = [
    "水理AIでも同レース注目。モデルの1着確率が突出してるので堅い一戦に見えます\n\nデータで裏付けが取れる予想は信頼できますね #競艇予想",
    "同意です。水理AIの特徴量分析でもモーター2連率と展示タイムが揃ってるレース\n\nこういう根拠のある予想、参考になります #ボートレース",
    "なるほど、この視点は面白い。水理AIだとモーター評価で別角度から見てますが、結論は同じでした\n\nやっぱり強い予想家の読みとAIが一致すると自信持てます",
    "水理AIのデータでも同じ結論。このレースは条件揃ってますね\n\nこういう堅いレースを見極めるの大事ですよね #競艇予想",
    "AI視点でも注目のレース。モーターと選手の相性がいい組み合わせですね\n\n予想の軸がしっかりしてて参考になります",
]

QUOTE_TEMPLATES_INFO = [
    "水理AIのデータベースでもこのレース注目してます。ML予測で推奨度ランク付きの全場分析を毎朝配信中\n\n#ボートレース #競艇AI予測",
    "このレース、水理AIの分析では注目度が高いです。データで見ると面白い一戦になりそう\n\n#競艇予想 #ボートレース",
    "水理AIでもチェックしてました。データ的に見どころ多いレースですね\n\n#ボートレース",
]

QUOTE_TEMPLATES = QUOTE_TEMPLATES_HIT + QUOTE_TEMPLATES_PREDICTION + QUOTE_TEMPLATES_INFO

REPLY_TEMPLATES_CONVERSATION = [
    "注目レースですね! モーターデータ的にも面白そうです。ちなみに展示タイムはチェックされましたか？",
    "さすがの読みですね。水理AIでも同じ結論でした。このレース、風の影響どう見てますか？",
    "データ分析でも堅い一戦に見えます。3連単の買い目、何点くらいで絞ってますか？",
    "同じく注目してました! インコースの信頼度が高いレースですよね。1号艇のモーターどう評価されてますか？",
    "このレースいいですよね。水理AIでも推奨度高めでした。2着争いが鍵だと思うんですけどどう見てますか？",
    "面白い予想ですね。水理AIだと少し違う結論なんですが、展示見てから最終判断する感じですか？",
]

REPLY_TEMPLATES_PRAISE = [
    "的中おめでとうございます! いつも精度高くて参考にしてます",
    "さすがです。このレースは難しかったのに見事な読みですね",
    "いつも勉強になります。データ分析やってる身として、この精度は本当にすごい",
    "見事です! 毎日チェックしてますがほんと安定してますね",
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


def _humanize_text(text: str) -> str:
    """Add subtle randomness to text so it doesn't look automated.

    - Randomly prepend a filler word
    - Randomly append a trailing phrase
    - Small chance of adding an emoji
    """
    # 30% chance to prepend a filler
    if random.random() < 0.3:
        filler = random.choice(_FILLERS)
        if filler:
            text = filler + text

    # 20% chance to append a trailing variation
    if random.random() < 0.2:
        trail = random.choice(_TRAIL_VARIATIONS)
        if trail:
            text = text.rstrip() + trail

    # 15% chance to add an emoji
    if random.random() < 0.15:
        emoji = random.choice(_EMOJI_POOL)
        if emoji:
            text = text.rstrip() + emoji

    return text


def _human_delay(dry_run: bool = False) -> None:
    """Random delay between actions to appear human."""
    if dry_run:
        return
    delay = random.uniform(ACTION_DELAY_MIN, ACTION_DELAY_MAX)
    time.sleep(delay)


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
    """Pick a quote template matched to the tweet content, with humanization."""
    category = _classify_tweet(tweet_text)
    if category == "hit":
        text = random.choice(QUOTE_TEMPLATES_HIT)
    elif category == "prediction":
        text = random.choice(QUOTE_TEMPLATES_PREDICTION)
    else:
        text = random.choice(QUOTE_TEMPLATES_INFO)
    return _humanize_text(text)


def pick_reply_template(tweet_text: str = "") -> str:
    """Pick a reply template. Prioritize conversation starters (75x weight)."""
    # 70% conversation (question-based), 30% praise
    if random.random() < 0.7:
        text = random.choice(REPLY_TEMPLATES_CONVERSATION)
    else:
        text = random.choice(REPLY_TEMPLATES_PRAISE)
    return _humanize_text(text)


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
    """Execute auto engagement routine with human-like randomness.

    Humanization:
      - Target order is shuffled each run
      - Each target has a random chance of being skipped
      - Each like has a random chance of being skipped
      - Quote RT and reply are not always paired
      - Random delays between actions
      - Template text has subtle variations

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

    # Shuffle target order (humans don't always engage in the same order)
    random.shuffle(scan_results)

    for target_data in scan_results:
        handle = target_data["handle"]
        tweets = target_data["tweets"]

        if not tweets:
            continue

        # Random chance to skip this target entirely
        if random.random() > TARGET_ENGAGE_PROB:
            log.info("Randomly skipping target @%s this run", handle)
            summary["skipped"] += 1
            continue

        # Like tweets randomly (not all of them)
        shuffled_tweets = list(tweets)
        random.shuffle(shuffled_tweets)
        for tweet in shuffled_tweets:
            if not can_like(race_date):
                break
            # Random chance to skip this particular like
            if random.random() > LIKE_PROB:
                continue
            _human_delay(dry_run)
            liked = like_tweet(tweet["id"], dry_run=dry_run)
            if liked or dry_run:
                if liked and not dry_run:
                    save_engagement_log(
                        "like", handle, race_date,
                        target_tweet_id=tweet["id"],
                    )
                summary["likes"] += 1

        # Pick the best tweet for quote RT
        best_tweet = max(
            tweets,
            key=lambda t: t.get("metrics", {}).get("like_count", 0)
            + t.get("metrics", {}).get("retweet_count", 0) * 2,
        )

        # Decide: quote only, reply only, or both
        do_quote = can_quote(race_date, handle)
        do_reply = can_reply(race_date)
        do_both = random.random() < BOTH_QUOTE_AND_REPLY_PROB

        if do_quote and do_reply and not do_both:
            # Pick one at random
            if random.random() < 0.6:  # Slight bias toward quote RT (higher value)
                do_reply = False
            else:
                do_quote = False

        # Quote RT
        if do_quote:
            _human_delay(dry_run)
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

        # Reply (to a different tweet if possible)
        if do_reply:
            _human_delay(dry_run)
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
