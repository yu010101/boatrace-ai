"""Tweet template generation for morning/hit/daily posts."""

from __future__ import annotations

from boatrace_ai.data.constants import STADIUMS

MAX_TWEET_LENGTH = 280


def _truncate(text: str, max_len: int = MAX_TWEET_LENGTH) -> str:
    """Truncate text to fit within tweet character limit."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def build_morning_tweet(
    race_date: str,
    s_rank_races: list[dict],
    note_url: str = "",
) -> str:
    """Build morning prediction tweet.

    Args:
        s_rank_races: List of dicts with stadium_number, race_number, grade
        note_url: URL to the note.com article
    """
    lines: list[str] = []
    lines.append(f"【AI予測】{race_date} 本日の推奨レース")
    lines.append("")

    if s_rank_races:
        s_labels = []
        for r in s_rank_races[:5]:  # max 5 to fit tweet
            stadium = STADIUMS.get(r["stadium_number"], str(r["stadium_number"]))
            s_labels.append(f"{stadium}{r['race_number']}R")
        lines.append(f"推奨度S: {', '.join(s_labels)}")
    else:
        lines.append("本日はSランク該当なし")

    lines.append("")
    if note_url:
        lines.append(f"詳細はこちら {note_url}")
    lines.append("#競艇AI予測 #ボートレース")

    return _truncate("\n".join(lines))


def build_hit_tweet(
    race_date: str,
    stadium_number: int,
    race_number: int,
    bet_type: str,
    combination: str,
    payout: int,
    grade: str = "",
) -> str:
    """Build hit (winning bet) announcement tweet."""
    stadium = STADIUMS.get(stadium_number, str(stadium_number))
    grade_label = f"(推奨度{grade}) " if grade else ""

    lines: list[str] = []
    lines.append(f"的中! {stadium}{race_number}R {bet_type} {combination} {grade_label}")
    lines.append(f"配当 ¥{payout:,}")
    lines.append("")
    lines.append(f"#競艇AI予測 #{stadium} #ボートレース")

    return _truncate("\n".join(lines))


def build_daily_tweet(
    race_date: str,
    total_races: int,
    hit_count: int,
    roi: float,
    note_url: str = "",
) -> str:
    """Build daily summary tweet."""
    roi_pct = int(roi * 100)

    lines: list[str] = []
    lines.append(f"【{race_date} 成績】")
    lines.append(f"{total_races}R中{hit_count}R的中 / 回収率{roi_pct}%")

    if roi >= 1.0:
        lines.append("プラス収支!")
    lines.append("")

    if note_url:
        lines.append(f"詳細 {note_url}")
    lines.append("#競艇AI予測 #ボートレース")

    return _truncate("\n".join(lines))
