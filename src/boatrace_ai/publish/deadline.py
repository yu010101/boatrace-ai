"""予想・仮想購入が、そのレースの締切より前に保存されたかの照合（2026-10-21 本人「照合して」）。

10/14〜10/21 の実測で、締切後に保存された予想が1日0〜16レースあり、答え合わせの的中に数えていた。
記事の数字は締切前に保存したものだけで出し、外した件数を書く。
締切は番組表（Boatrace Open API の race_closed_at、日本時間・タイムゾーン無し "YYYY-MM-DD HH:MM:SS"）。
保存時刻は DB の created_at（SQLite datetime('now') ＝ UTC）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def parse_utc(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_close(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
    except (TypeError, ValueError):
        return None


def before_deadline(created_at_utc: str, close: datetime | None) -> bool:
    """締切がわからない・保存時刻が読めないものは「締切前」と扱わない（数えない側に倒す）"""
    made = parse_utc(created_at_utc)
    return bool(made and close and made < close)


async def closed_map(race_date: str) -> dict[tuple[int, int], datetime]:
    """その日の各レースの締切（場番号, レース番号）→ 日時"""
    from boatrace_ai.data.client import fetch_programs

    resp = await fetch_programs(date.fromisoformat(race_date))
    out: dict[tuple[int, int], datetime] = {}
    for p in resp.programs:
        c = parse_close(p.race_closed_at)
        if c:
            out[(p.race_stadium_number, p.race_number)] = c
    return out


def split_records(records: list[dict], made_at: dict[tuple[int, int], str], close: dict[tuple[int, int], datetime]) -> tuple[list[dict], list[dict]]:
    """答え合わせの行を、締切前に保存された予想のものと、それ以外に分ける"""
    keep, drop = [], []
    for r in records:
        k = (r["stadium_number"], r["race_number"])
        (keep if before_deadline(made_at.get(k, ""), close.get(k)) else drop).append(r)
    return keep, drop


def roi_before_deadline(bets: list[dict], close: dict[tuple[int, int], datetime]) -> tuple[dict, int]:
    """判定済みの仮想購入のうち、締切前に保存されたものだけで収支を出す。戻り値は (get_roi_stats と同じ形, 外した点数)"""
    kept = [b for b in bets if b.get("is_hit") is not None and before_deadline(b.get("created_at", ""), close.get((b["stadium_number"], b["race_number"])))]
    dropped = sum(1 for b in bets if b.get("is_hit") is not None) - len(kept)
    inv = sum(b["bet_amount"] for b in kept)
    pay = sum(b["payout"] for b in kept)
    hits = sum(1 for b in kept if b["is_hit"] == 1)
    return {
        "total_bets": len(kept), "total_invested": inv, "total_payout": pay, "profit": pay - inv,
        "roi": pay / inv if inv else 0.0, "hit_count": hits, "hit_rate": hits / len(kept) if kept else 0.0,
    }, dropped
