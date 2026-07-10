"""展示タイム取得 (boatrace.jp beforeinfo ページ)"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup


async def fetch_exhibition(
    race_no: int, stadium_code: str, date: str
) -> dict[int, float]:
    """展示タイムを取得。

    Args:
        race_no: レース番号 (1-12)
        stadium_code: 場コード (01-24)
        date: 日付 YYYYMMDD形式

    Returns:
        {boat_number: time_seconds} の辞書。取得失敗艇は含まない。
    """
    url = (
        f"https://www.boatrace.jp/owpc/pc/race/beforeinfo"
        f"?rno={race_no}&jcd={stadium_code}&hd={date}"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    times: dict[int, float] = {}
    for i, tbody in enumerate(soup.select("table.is-w748 tbody"), 1):
        td = tbody.select_one("td[rowspan]")
        if td:
            try:
                times[i] = float(td.text.strip())
            except ValueError:
                pass
    return times
