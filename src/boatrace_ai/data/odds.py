"""Odds scraper for boatrace.jp.

Fetches win/exacta/quinella/trifecta/trio odds from the official website.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from boatrace_ai import config

log = logging.getLogger(__name__)

_BASE = "https://www.boatrace.jp/owpc/pc/race"
_REQUEST_INTERVAL = 1.0  # seconds between requests


@dataclass
class OddsData:
    """Parsed odds for a single race."""

    win: dict[int, float] = field(default_factory=dict)  # {1: 2.3, 2: 8.5, ...}
    exacta: dict[str, float] = field(default_factory=dict)  # {"1-3": 15.2, ...}
    quinella: dict[str, float] = field(default_factory=dict)  # {"1-3": 8.0, ...}
    trifecta: dict[str, float] = field(default_factory=dict)  # {"1-2-3": 51.4, ...}
    trio: dict[str, float] = field(default_factory=dict)  # {"1-2-3": 12.0, ...}
    fetched_at: str = ""


def _parse_odds_value(text: str) -> float | None:
    """Parse an odds string like '4.6' or '1035'. Returns None for non-numeric."""
    text = text.strip().replace(",", "")
    if not text or text == "-" or text == "欠場":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _ensure_bs4():
    """Check beautifulsoup4 is installed."""
    try:
        import bs4  # noqa: F401
    except ImportError:
        raise ImportError(
            "オッズ取得には beautifulsoup4 が必要です。\n"
            "pip install beautifulsoup4 でインストールしてください。"
        )


async def _fetch_html(url: str, client: httpx.AsyncClient) -> str | None:
    """Fetch HTML from a URL. Returns None on failure."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        log.warning("Odds fetch failed (network): %s — %s", url, e)
        return None
    except httpx.HTTPStatusError as e:
        log.warning("Odds fetch failed (HTTP %d): %s", e.response.status_code, url)
        return None


def _parse_win_odds(html: str) -> dict[int, float]:
    """Parse win (単勝) odds from the oddstf page HTML.

    Structure:
        <td class="is-boatColor{N}">{N}</td>
        <td>racer name</td>
        <td class="oddsPoint">{odds}</td>
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    odds: dict[int, float] = {}

    # Find the 単勝オッズ section
    win_header = soup.find("span", class_="title7_mainLabel", string="単勝オッズ")
    if not win_header:
        return odds

    # The table is in the parent grid_unit div
    grid_unit = win_header.find_parent("div", class_="grid_unit")
    if not grid_unit:
        return odds

    table = grid_unit.find("table")
    if not table:
        return odds

    for tbody in table.find_all("tbody"):
        row = tbody.find("tr")
        if not row:
            continue
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # First cell: boat number, third cell: odds
        boat_cell = cells[0]
        odds_cell = cells[2]

        # Extract boat number from class (is-boatColor1..6)
        boat_num = None
        for cls in boat_cell.get("class", []):
            if cls.startswith("is-boatColor"):
                try:
                    boat_num = int(cls.replace("is-boatColor", ""))
                except ValueError:
                    pass

        if boat_num is None:
            continue

        val = _parse_odds_value(odds_cell.get_text())
        if val is not None:
            odds[boat_num] = val

    return odds


def _extract_header_boats(thead) -> list[int]:
    """Extract boat numbers from thead, skipping name columns (is-borderLeftNone)."""
    header_boats: list[int] = []
    for th in thead.find_all("th"):
        classes = th.get("class", [])
        # Skip name columns that have is-borderLeftNone
        if "is-borderLeftNone" in classes:
            continue
        for cls in classes:
            if cls.startswith("is-boatColor"):
                try:
                    header_boats.append(int(cls.replace("is-boatColor", "")))
                except ValueError:
                    pass
    return header_boats


def _find_table_after_header(soup, header_text: str):
    """Find the table element that follows a title7 header with given text."""
    header = soup.find("span", class_="title7_mainLabel", string=header_text)
    if not header:
        return None, None

    # The table is in a sibling div of the title7 parent, or in an ancestor div
    # Walk up to the title7 div, then find the next table
    title_div = header.find_parent("div", class_="title7")
    if title_div:
        # Look for next sibling that contains a table
        for sibling in title_div.find_next_siblings():
            table = sibling.find("table") if sibling.name != "table" else sibling
            if table:
                return header, table

    # Fallback: find in the containing div
    outer_div = header.find_parent("div")
    while outer_div:
        table = outer_div.find("table")
        if table:
            return header, table
        outer_div = outer_div.find_parent("div")

    return header, None


def _parse_exacta_odds(html: str) -> dict[str, float]:
    """Parse exacta (2連単) odds from the odds2tf page.

    Table structure: 6 columns (1st-place boats), 5 rows each (2nd-place boats).
    Column header has boat N, row cell has partner boat M, then odds.
    Result key: "N-M" (N=1st, M=2nd).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    odds: dict[str, float] = {}

    _, table = _find_table_after_header(soup, "2連単オッズ")
    if not table:
        return odds

    # Header row has the 1st-place boat numbers
    thead = table.find("thead")
    if not thead:
        return odds

    header_boats = _extract_header_boats(thead)

    if len(header_boats) < 2:
        return odds

    # Parse body rows
    tbody = table.find("tbody", class_="is-p3-0")
    if not tbody:
        return odds

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        # Each row has pairs: [partner_boat, odds] × N columns
        col_idx = 0
        i = 0
        while i < len(cells) and col_idx < len(header_boats):
            cell = cells[i]
            classes = cell.get("class", [])

            # Check if this is a boat number cell
            is_boat = any(c.startswith("is-boatColor") for c in classes)
            is_odds = "oddsPoint" in classes

            if is_boat and not is_odds:
                partner = cell.get_text().strip()
                # Next cell should be odds
                if i + 1 < len(cells):
                    odds_cell = cells[i + 1]
                    val = _parse_odds_value(odds_cell.get_text())
                    if val is not None and partner.isdigit():
                        first = header_boats[col_idx]
                        second = int(partner)
                        odds[f"{first}-{second}"] = val
                    col_idx += 1
                    i += 2
                else:
                    i += 1
            else:
                i += 1

    return odds


def _parse_quinella_odds(html: str) -> dict[str, float]:
    """Parse quinella (2連複) odds from the odds2tf page.

    Same table structure as exacta but for unordered pairs.
    Keys use smaller-larger format: "1-3".
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    odds: dict[str, float] = {}

    _, table = _find_table_after_header(soup, "2連複オッズ")
    if not table:
        return odds

    # Header boats
    thead = table.find("thead")
    if not thead:
        return odds

    header_boats = _extract_header_boats(thead)

    if len(header_boats) < 2:
        return odds

    tbody = table.find("tbody", class_="is-p3-0")
    if not tbody:
        return odds

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        col_idx = 0
        i = 0
        while i < len(cells) and col_idx < len(header_boats):
            cell = cells[i]
            classes = cell.get("class", [])
            is_boat = any(c.startswith("is-boatColor") for c in classes)
            is_odds = "oddsPoint" in classes

            if is_boat and not is_odds:
                partner = cell.get_text().strip()
                if i + 1 < len(cells):
                    odds_cell = cells[i + 1]
                    val = _parse_odds_value(odds_cell.get_text())
                    if val is not None and partner.isdigit():
                        a = header_boats[col_idx]
                        b = int(partner)
                        # Normalize to smaller-larger
                        key = f"{min(a, b)}-{max(a, b)}"
                        if key not in odds:
                            odds[key] = val
                    col_idx += 1
                    i += 2
                else:
                    i += 1
            elif is_odds:
                # Empty cell in quinella table (diagonal)
                col_idx += 1
                i += 1
            else:
                i += 1

    return odds


def _parse_trifecta_odds(html: str) -> dict[str, float]:
    """Parse trifecta (3連単) odds from the odds3t page.

    Table: 6 major columns (1st-place), each has groups of (2nd, 3rd, odds).
    2nd-place cells have rowspan=4, with 4 3rd-place options each.
    Total: 6 × 5 × 4 = 120 combinations.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    odds: dict[str, float] = {}

    # Find all tbody with is-p3-0 class (odds body)
    bodies = soup.find_all("tbody", class_="is-p3-0")
    if not bodies:
        return odds

    # The 3連単 page has the header row identifying 1st-place boats
    # Boats are always 1-6 in column order
    first_boats = [1, 2, 3, 4, 5, 6]

    for tbody in bodies:
        rows = tbody.find_all("tr")
        # Track current 2nd-place boat per column
        current_2nd: dict[int, int] = {}

        for row in rows:
            cells = row.find_all("td")
            col_idx = 0
            i = 0

            while i < len(cells) and col_idx < 6:
                cell = cells[i]
                classes = cell.get("class", [])
                is_boat = any(c.startswith("is-boatColor") for c in classes)
                is_border_left = "is-borderLeftNone" in classes
                has_rowspan = cell.get("rowspan") is not None

                if is_boat and has_rowspan:
                    # This is a 2nd-place boat (rowspan=4)
                    boat_text = cell.get_text().strip()
                    if boat_text.isdigit():
                        current_2nd[col_idx] = int(boat_text)
                    i += 1
                elif is_boat and not has_rowspan and "oddsPoint" not in classes:
                    # This is a 3rd-place boat
                    third_text = cell.get_text().strip()
                    if i + 1 < len(cells):
                        odds_cell = cells[i + 1]
                        val = _parse_odds_value(odds_cell.get_text())
                        if val is not None and third_text.isdigit() and col_idx in current_2nd:
                            first = first_boats[col_idx]
                            second = current_2nd[col_idx]
                            third = int(third_text)
                            odds[f"{first}-{second}-{third}"] = val
                        col_idx += 1
                        i += 2
                    else:
                        i += 1
                elif "oddsPoint" in classes:
                    # Standalone odds cell (shouldn't happen in normal flow)
                    col_idx += 1
                    i += 1
                else:
                    i += 1

    return odds


def _parse_trio_odds(html: str) -> dict[str, float]:
    """Parse trio (3連複) odds from the odds3f page.

    Similar structure to trifecta but for unordered combinations.
    Keys use sorted format: "1-2-3".
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    odds: dict[str, float] = {}

    # Find all odds cells directly
    odds_cells = soup.find_all("td", class_="oddsPoint")
    if not odds_cells:
        return odds

    # The 3連複 page has a simpler layout:
    # Combinations listed as "1=2=3" style in separate cells
    # Let's try the table approach similar to trifecta
    bodies = soup.find_all("tbody", class_="is-p3-0")
    if not bodies:
        return odds

    first_boats = [1, 2, 3, 4, 5, 6]

    for tbody in bodies:
        rows = tbody.find_all("tr")
        current_2nd: dict[int, int] = {}

        for row in rows:
            cells = row.find_all("td")
            col_idx = 0
            i = 0

            while i < len(cells) and col_idx < 6:
                cell = cells[i]
                classes = cell.get("class", [])
                is_boat = any(c.startswith("is-boatColor") for c in classes)
                has_rowspan = cell.get("rowspan") is not None

                if is_boat and has_rowspan:
                    boat_text = cell.get_text().strip()
                    if boat_text.isdigit():
                        current_2nd[col_idx] = int(boat_text)
                    i += 1
                elif is_boat and not has_rowspan and "oddsPoint" not in classes:
                    third_text = cell.get_text().strip()
                    if i + 1 < len(cells):
                        odds_cell = cells[i + 1]
                        val = _parse_odds_value(odds_cell.get_text())
                        if val is not None and third_text.isdigit() and col_idx in current_2nd:
                            boats = sorted([first_boats[col_idx], current_2nd[col_idx], int(third_text)])
                            key = f"{boats[0]}-{boats[1]}-{boats[2]}"
                            if key not in odds:
                                odds[key] = val
                        col_idx += 1
                        i += 2
                    else:
                        i += 1
                elif "oddsPoint" in classes:
                    col_idx += 1
                    i += 1
                else:
                    i += 1

    return odds


async def fetch_odds(
    race_number: int,
    stadium_number: int,
    race_date: str,
) -> OddsData | None:
    """Fetch all odds for a single race from boatrace.jp.

    Args:
        race_number: Race number (1-12).
        stadium_number: Stadium number (1-24).
        race_date: Date string "YYYY-MM-DD".

    Returns:
        OddsData with parsed odds, or None on complete failure.
    """
    _ensure_bs4()

    hd = race_date.replace("-", "")
    jcd = f"{stadium_number:02d}"
    rno = str(race_number)

    urls = {
        "win": f"{_BASE}/oddstf?rno={rno}&jcd={jcd}&hd={hd}",
        "exacta": f"{_BASE}/odds2tf?rno={rno}&jcd={jcd}&hd={hd}",
        "trifecta": f"{_BASE}/odds3t?rno={rno}&jcd={jcd}&hd={hd}",
        "trio": f"{_BASE}/odds3f?rno={rno}&jcd={jcd}&hd={hd}",
    }

    result = OddsData(fetched_at=datetime.now().isoformat())

    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        # Fetch win + place odds (single page)
        html = await _fetch_html(urls["win"], client)
        if html:
            result.win = _parse_win_odds(html)
        else:
            log.warning("Failed to fetch win odds for stadium=%d race=%d", stadium_number, race_number)
            return None  # Win odds are essential

        await asyncio.sleep(_REQUEST_INTERVAL)

        # Fetch exacta + quinella (single page)
        html = await _fetch_html(urls["exacta"], client)
        if html:
            result.exacta = _parse_exacta_odds(html)
            result.quinella = _parse_quinella_odds(html)

        await asyncio.sleep(_REQUEST_INTERVAL)

        # Fetch trifecta
        html = await _fetch_html(urls["trifecta"], client)
        if html:
            result.trifecta = _parse_trifecta_odds(html)

        await asyncio.sleep(_REQUEST_INTERVAL)

        # Fetch trio
        html = await _fetch_html(urls["trio"], client)
        if html:
            result.trio = _parse_trio_odds(html)

    if not result.win:
        log.warning("No win odds parsed for stadium=%d race=%d", stadium_number, race_number)
        return None

    log.info(
        "Odds fetched: stadium=%d race=%d win=%d exacta=%d quinella=%d trifecta=%d trio=%d",
        stadium_number,
        race_number,
        len(result.win),
        len(result.exacta),
        len(result.quinella),
        len(result.trifecta),
        len(result.trio),
    )

    return result
