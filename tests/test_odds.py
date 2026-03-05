"""Tests for data/odds.py — odds scraper with HTML mocks."""

from __future__ import annotations

import pytest

from boatrace_ai.data.odds import (
    OddsData,
    _parse_exacta_odds,
    _parse_odds_value,
    _parse_quinella_odds,
    _parse_trifecta_odds,
    _parse_trio_odds,
    _parse_win_odds,
)


# ── _parse_odds_value ────────────────────────────────────


def test_parse_odds_normal() -> None:
    assert _parse_odds_value("4.6") == 4.6


def test_parse_odds_integer() -> None:
    assert _parse_odds_value("1035") == 1035.0


def test_parse_odds_with_comma() -> None:
    assert _parse_odds_value("1,035") == 1035.0


def test_parse_odds_dash() -> None:
    assert _parse_odds_value("-") is None


def test_parse_odds_empty() -> None:
    assert _parse_odds_value("") is None


def test_parse_odds_absent() -> None:
    assert _parse_odds_value("欠場") is None


# ── Win odds parsing ─────────────────────────────────────

WIN_HTML = """
<div class="grid_unit">
    <div class="title7">
        <h3 class="title7_title">
            <span class="title7_mainLabel">単勝オッズ</span>
        </h3>
    </div>
    <div class="table1">
        <table class="is-w495">
            <thead>
                <tr class="is-fs14"><th> </th><th>ボートレーサー</th><th>単勝オッズ</th></tr>
            </thead>
            <tbody><tr>
                <td class="is-fs14 is-fBold is-boatColor1">1</td>
                <td class="is-p20-0"><span>選手A</span></td>
                <td class="oddsPoint ">4.6</td>
            </tr></tbody>
            <tbody><tr>
                <td class="is-fs14 is-fBold is-boatColor2">2</td>
                <td class="is-p20-0"><span>選手B</span></td>
                <td class="oddsPoint ">2.3</td>
            </tr></tbody>
            <tbody><tr>
                <td class="is-fs14 is-fBold is-boatColor3">3</td>
                <td class="is-p20-0"><span>選手C</span></td>
                <td class="oddsPoint ">2.6</td>
            </tr></tbody>
            <tbody><tr>
                <td class="is-fs14 is-fBold is-boatColor4">4</td>
                <td class="is-p20-0"><span>選手D</span></td>
                <td class="oddsPoint ">5.5</td>
            </tr></tbody>
            <tbody><tr>
                <td class="is-fs14 is-fBold is-boatColor5">5</td>
                <td class="is-p20-0"><span>選手E</span></td>
                <td class="oddsPoint ">10.6</td>
            </tr></tbody>
            <tbody><tr>
                <td class="is-fs14 is-fBold is-boatColor6">6</td>
                <td class="is-p20-0"><span>選手F</span></td>
                <td class="oddsPoint ">23.1</td>
            </tr></tbody>
        </table>
    </div>
</div>
"""


def test_parse_win_odds() -> None:
    odds = _parse_win_odds(WIN_HTML)
    assert len(odds) == 6
    assert odds[1] == 4.6
    assert odds[2] == 2.3
    assert odds[6] == 23.1


def test_parse_win_odds_empty() -> None:
    odds = _parse_win_odds("<html><body></body></html>")
    assert odds == {}


# ── Exacta odds parsing ─────────────────────────────────

EXACTA_HTML = """
<div>
    <div class="title7">
        <h3 class="title7_title">
            <span class="title7_mainLabel">2連単オッズ</span>
        </h3>
    </div>
    <div class="table1">
        <table>
            <thead class="is-p15-7 is-fs14">
                <tr>
                    <th class="is-boatColor1">1</th>
                    <th class="is-boatColor1 is-borderLeftNone">選手A</th>
                    <th class="is-boatColor2">2</th>
                    <th class="is-boatColor2 is-borderLeftNone">選手B</th>
                    <th class="is-boatColor3">3</th>
                    <th class="is-boatColor3 is-borderLeftNone">選手C</th>
                </tr>
            </thead>
            <tbody class="is-p3-0">
                <tr>
                    <td class="is-fs14 is-boatColor2 is-borderLeftNone">2</td>
                    <td class="oddsPoint ">21.4</td>
                    <td class="is-fs14 is-boatColor1">1</td>
                    <td class="oddsPoint ">19.7</td>
                    <td class="is-fs14 is-boatColor1">1</td>
                    <td class="oddsPoint ">16.2</td>
                </tr>
                <tr>
                    <td class="is-fs14 is-boatColor3 is-borderLeftNone">3</td>
                    <td class="oddsPoint ">16.3</td>
                    <td class="is-fs14 is-boatColor3">3</td>
                    <td class="oddsPoint ">7.4</td>
                    <td class="is-fs14 is-boatColor2">2</td>
                    <td class="oddsPoint ">8.2</td>
                </tr>
            </tbody>
        </table>
    </div>
</div>
"""


def test_parse_exacta_odds() -> None:
    odds = _parse_exacta_odds(EXACTA_HTML)
    assert odds["1-2"] == 21.4  # Column 1, partner 2
    assert odds["1-3"] == 16.3  # Column 1, partner 3
    assert odds["2-1"] == 19.7  # Column 2, partner 1
    assert odds["2-3"] == 7.4  # Column 2, partner 3
    assert odds["3-1"] == 16.2  # Column 3, partner 1
    assert odds["3-2"] == 8.2  # Column 3, partner 2


# ── Quinella odds parsing ────────────────────────────────

QUINELLA_HTML = """
<div>
    <div class="title7">
        <h3 class="title7_title">
            <span class="title7_mainLabel">2連複オッズ</span>
        </h3>
    </div>
    <div class="table1">
        <table>
            <thead class="is-p15-7 is-fs14">
                <tr>
                    <th class="is-boatColor1">1</th>
                    <th class="is-boatColor1 is-borderLeftNone">選手A</th>
                    <th class="is-boatColor2">2</th>
                    <th class="is-boatColor2 is-borderLeftNone">選手B</th>
                    <th class="is-boatColor3">3</th>
                    <th class="is-boatColor3 is-borderLeftNone">選手C</th>
                </tr>
            </thead>
            <tbody class="is-p3-0">
                <tr>
                    <td class="is-fs14 is-boatColor2 is-borderLeftNone">2</td>
                    <td class="oddsPoint ">10.5</td>
                    <td class="is-fs14 is-boatColor3">3</td>
                    <td class="oddsPoint ">5.2</td>
                    <td class="oddsPoint "></td>
                    <td class="oddsPoint "></td>
                </tr>
                <tr>
                    <td class="is-fs14 is-boatColor3 is-borderLeftNone">3</td>
                    <td class="oddsPoint ">8.3</td>
                    <td class="oddsPoint "></td>
                    <td class="oddsPoint "></td>
                    <td class="oddsPoint "></td>
                    <td class="oddsPoint "></td>
                </tr>
            </tbody>
        </table>
    </div>
</div>
"""


def test_parse_quinella_odds() -> None:
    odds = _parse_quinella_odds(QUINELLA_HTML)
    assert odds["1-2"] == 10.5  # 1=2
    assert odds["1-3"] == 8.3  # 1=3
    assert odds["2-3"] == 5.2  # 2=3


# ── Trifecta odds parsing ───────────────────────────────

TRIFECTA_HTML = """
<div>
    <table>
        <tbody class="is-p3-0">
            <tr>
                <td class="is-fs14 is-boatColor2 is-borderLeftNone" rowspan="2">2</td>
                <td class="is-boatColor2">3</td>
                <td class="oddsPoint ">51.4</td>
                <td class="is-fs14 is-boatColor1" rowspan="2">1</td>
                <td class="is-boatColor1">3</td>
                <td class="oddsPoint ">70.7</td>
            </tr>
            <tr>
                <td class="is-boatColor2">4</td>
                <td class="oddsPoint ">64.4</td>
                <td class="is-boatColor1">4</td>
                <td class="oddsPoint ">72.4</td>
            </tr>
            <tr>
                <td class="is-fs14 is-boatColor3 is-borderLeftNone" rowspan="2">3</td>
                <td class="is-boatColor3">2</td>
                <td class="oddsPoint ">45.0</td>
                <td class="is-fs14 is-boatColor3" rowspan="2">3</td>
                <td class="is-boatColor3">1</td>
                <td class="oddsPoint ">40.0</td>
            </tr>
            <tr>
                <td class="is-boatColor3">4</td>
                <td class="oddsPoint ">88.8</td>
                <td class="is-boatColor3">4</td>
                <td class="oddsPoint ">95.5</td>
            </tr>
        </tbody>
    </table>
</div>
"""


def test_parse_trifecta_odds() -> None:
    odds = _parse_trifecta_odds(TRIFECTA_HTML)
    # Column 1 (boat 1): 2nd=2, 3rd=3 → 1-2-3
    assert odds["1-2-3"] == 51.4
    # Column 1: 2nd=2, 3rd=4 → 1-2-4
    assert odds["1-2-4"] == 64.4
    # Column 1: 2nd=3, 3rd=2 → 1-3-2
    assert odds["1-3-2"] == 45.0
    # Column 1: 2nd=3, 3rd=4 → 1-3-4
    assert odds["1-3-4"] == 88.8
    # Column 2 (boat 2): 2nd=1, 3rd=3 → 2-1-3
    assert odds["2-1-3"] == 70.7
    # Column 2: 2nd=1, 3rd=4 → 2-1-4
    assert odds["2-1-4"] == 72.4
    # Column 2: 2nd=3, 3rd=1 → 2-3-1
    assert odds["2-3-1"] == 40.0
    # Column 2: 2nd=3, 3rd=4 → 2-3-4
    assert odds["2-3-4"] == 95.5


# ── Trio odds parsing ──────────────────────────────────

# Trio uses same table structure as trifecta but combinations are sorted
TRIO_HTML = """
<div>
    <table>
        <tbody class="is-p3-0">
            <tr>
                <td class="is-fs14 is-boatColor2 is-borderLeftNone" rowspan="2">2</td>
                <td class="is-boatColor2">3</td>
                <td class="oddsPoint ">5.4</td>
                <td class="is-fs14 is-boatColor1" rowspan="2">1</td>
                <td class="is-boatColor1">3</td>
                <td class="oddsPoint ">7.2</td>
            </tr>
            <tr>
                <td class="is-boatColor2">4</td>
                <td class="oddsPoint ">12.8</td>
                <td class="is-boatColor1">4</td>
                <td class="oddsPoint ">15.3</td>
            </tr>
        </tbody>
    </table>
</div>
"""


def test_parse_trio_odds() -> None:
    odds = _parse_trio_odds(TRIO_HTML)
    # Column 1 (boat 1): 2nd=2, 3rd=3 → sorted 1-2-3
    assert odds["1-2-3"] == 5.4
    # Column 1: 2nd=2, 3rd=4 → sorted 1-2-4
    assert odds["1-2-4"] == 12.8
    # Column 2 (boat 2): 2nd=1, 3rd=3 → sorted 1-2-3 (already seen, first wins)
    assert odds["1-2-3"] == 5.4
    # Column 2: 2nd=1, 3rd=4 → sorted 1-2-4 (already seen)
    assert odds["1-2-4"] == 12.8


def test_parse_trio_odds_empty() -> None:
    odds = _parse_trio_odds("<html><body></body></html>")
    assert odds == {}


# ── OddsData ─────────────────────────────────────────────


def test_odds_data_defaults() -> None:
    data = OddsData()
    assert data.win == {}
    assert data.exacta == {}
    assert data.fetched_at == ""
