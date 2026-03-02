"""Tests for tracking/roi.py — virtual betting and ROI calculation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from boatrace_ai.storage.database import (
    get_roi_daily,
    get_roi_stats,
    init_db,
    save_result,
    save_virtual_bets,
    update_virtual_bet,
)
from boatrace_ai.tracking.roi import (
    _normalize_combination,
    calculate_roi,
    check_virtual_bets,
    match_bet_to_payout,
    parse_bet_string,
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    with patch("boatrace_ai.storage.database.config") as mock_config:
        mock_config.DB_PATH = db_path
        init_db()
        yield mock_config


# ── parse_bet_string ──────────────────────────────────────


def test_parse_bet_string_trifecta() -> None:
    result = parse_bet_string("3連単 1-3-2")
    assert result == ("3連単", "1-3-2")


def test_parse_bet_string_quinella() -> None:
    result = parse_bet_string("2連複 1=3")
    assert result == ("2連複", "1=3")


def test_parse_bet_string_win() -> None:
    result = parse_bet_string("単勝 1")
    assert result == ("単勝", "1")


def test_parse_bet_string_invalid() -> None:
    assert parse_bet_string("invalid") is None


def test_parse_bet_string_unknown_type() -> None:
    assert parse_bet_string("枠連 1-2") is None


# ── _normalize_combination ────────────────────────────────


def test_normalize_ordered() -> None:
    """Ordered combination stays as-is."""
    assert _normalize_combination("1-3-2") == ["1-3-2"]


def test_normalize_unordered_pair() -> None:
    """Unordered pair expands to 2 permutations."""
    result = _normalize_combination("1=3")
    assert set(result) == {"1-3", "3-1"}


def test_normalize_unordered_triple() -> None:
    """Unordered triple expands to 6 permutations."""
    result = _normalize_combination("1=2=3")
    assert len(result) == 6
    assert "1-2-3" in result
    assert "3-2-1" in result


# ── match_bet_to_payout ──────────────────────────────────


def _payouts_json(**kwargs) -> str:
    """Build a payouts JSON string."""
    base = {
        "trifecta": [], "trio": [], "exacta": [],
        "quinella": [], "quinella_place": [],
        "win": [], "place": [],
    }
    base.update(kwargs)
    return json.dumps(base)


def test_match_trifecta_hit() -> None:
    payouts = _payouts_json(trifecta=[{"combination": "1-3-2", "payout": 1500}])
    result = match_bet_to_payout("3連単", "1-3-2", payouts)
    # 1500 * 10 = 15000
    assert result == 15000


def test_match_trifecta_miss() -> None:
    payouts = _payouts_json(trifecta=[{"combination": "3-1-2", "payout": 1500}])
    result = match_bet_to_payout("3連単", "1-3-2", payouts)
    assert result == 0


def test_match_quinella_hit() -> None:
    """Unordered bet '1=3' should match '1-3' in quinella payouts."""
    payouts = _payouts_json(quinella=[{"combination": "1-3", "payout": 800}])
    result = match_bet_to_payout("2連複", "1=3", payouts)
    assert result == 8000


def test_match_quinella_hit_reverse() -> None:
    """'1=3' should also match '3-1'."""
    payouts = _payouts_json(quinella=[{"combination": "3-1", "payout": 800}])
    result = match_bet_to_payout("2連複", "1=3", payouts)
    assert result == 8000


def test_match_trio_hit() -> None:
    """'1=2=3' should match any permutation in trio payouts."""
    payouts = _payouts_json(trio=[{"combination": "3-2-1", "payout": 500}])
    result = match_bet_to_payout("3連複", "1=2=3", payouts)
    assert result == 5000


def test_match_win_hit() -> None:
    payouts = _payouts_json(win=[{"combination": "1", "payout": 200}])
    result = match_bet_to_payout("単勝", "1", payouts)
    assert result == 2000


def test_match_unknown_bet_type() -> None:
    payouts = _payouts_json()
    result = match_bet_to_payout("枠連", "1-2", payouts)
    assert result == 0


def test_match_invalid_json() -> None:
    result = match_bet_to_payout("3連単", "1-3-2", "NOT JSON")
    assert result == 0


def test_match_none_json() -> None:
    result = match_bet_to_payout("3連単", "1-3-2", None)  # type: ignore[arg-type]
    assert result == 0


# ── calculate_roi ─────────────────────────────────────────


def test_calculate_roi_profit() -> None:
    assert calculate_roi(10000, 15000) == 1.5


def test_calculate_roi_loss() -> None:
    assert calculate_roi(10000, 5000) == 0.5


def test_calculate_roi_break_even() -> None:
    assert calculate_roi(10000, 10000) == 1.0


def test_calculate_roi_zero_invested() -> None:
    assert calculate_roi(0, 5000) == 0.0


# ── DB operations (save_virtual_bets, roi stats) ──────────


def test_save_virtual_bets() -> None:
    bets = ["3連単 1-3-2", "2連複 1=3"]
    save_virtual_bets("2026-02-28", 1, 1, bets, grade="S")

    # Check they were saved
    from boatrace_ai.storage.database import _get_connection
    conn = _get_connection()
    rows = conn.execute("SELECT * FROM virtual_bets").fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0]["bet_type"] == "3連単"
    assert rows[0]["combination"] == "1-3-2"
    assert rows[0]["bet_amount"] == 1000
    assert rows[0]["grade"] == "S"
    assert rows[0]["is_hit"] is None


def test_save_virtual_bets_invalid_format() -> None:
    """Invalid bet string should be skipped."""
    bets = ["invalid", "3連単 1-3-2"]
    save_virtual_bets("2026-02-28", 1, 1, bets)

    from boatrace_ai.storage.database import _get_connection
    conn = _get_connection()
    rows = conn.execute("SELECT * FROM virtual_bets").fetchall()
    conn.close()

    assert len(rows) == 1


def test_get_roi_stats_empty() -> None:
    stats = get_roi_stats("2026-01-01")
    assert stats["total_bets"] == 0
    assert stats["roi"] == 0.0


def test_get_roi_daily() -> None:
    save_virtual_bets("2026-02-28", 1, 1, ["3連単 1-3-2"])
    # Manually mark as hit
    from boatrace_ai.storage.database import _get_connection
    conn = _get_connection()
    conn.execute("UPDATE virtual_bets SET is_hit = 1, payout = 15000 WHERE id = 1")
    conn.commit()
    conn.close()

    daily = get_roi_daily("2026-02-28")
    assert daily["total_bets"] == 1
    assert daily["total_invested"] == 1000
    assert daily["total_payout"] == 15000
    assert daily["profit"] == 14000
    assert daily["roi"] == 15.0
    assert daily["hit_count"] == 1


def test_check_virtual_bets_full_flow() -> None:
    """End-to-end: save bets → save results → check bets."""
    from boatrace_ai.data.models import RaceResult

    # Save virtual bets
    save_virtual_bets("2026-02-28", 1, 1, ["3連単 1-3-2", "単勝 1"])

    # Save result with matching payouts
    boats = []
    for i, boat_num in enumerate([1, 2, 3, 4, 5, 6]):
        boats.append({
            "racer_boat_number": boat_num,
            "racer_course_number": boat_num,
            "racer_start_timing": 0.15,
            "racer_place_number": [1, 3, 2, 5, 4, 6].index(boat_num) + 1,
            "racer_number": 1000 + boat_num,
            "racer_name": f"選手{boat_num}",
        })
    result = RaceResult.model_validate({
        "race_date": "2026-02-28",
        "race_stadium_number": 1,
        "race_number": 1,
        "boats": boats,
        "payouts": {
            "trifecta": [{"combination": "1-3-2", "payout": 1500}],
            "trio": [],
            "exacta": [],
            "quinella": [],
            "quinella_place": [],
            "win": [{"combination": "1", "payout": 200}],
            "place": [],
        },
    })
    save_result("2026-02-28", result)

    # Check bets
    checked = check_virtual_bets()
    assert len(checked) == 2

    hits = [c for c in checked if c["is_hit"] == 1]
    assert len(hits) == 2  # Both should hit

    # Trifecta: 1500 * 10 = 15000
    trifecta = next(c for c in checked if c["bet_type"] == "3連単")
    assert trifecta["payout"] == 15000

    # Win: 200 * 10 = 2000
    win = next(c for c in checked if c["bet_type"] == "単勝")
    assert win["payout"] == 2000
