"""Tests for ml/backtest.py — backtest simulation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from boatrace_ai.ml.backtest import (
    _payouts_to_odds,
    _simulate_ev_strategy,
    _simulate_old_strategy,
    run_backtest,
)
from boatrace_ai.storage.database import init_db, save_prediction, save_result


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    with patch("boatrace_ai.storage.database.config") as mock_config:
        mock_config.DB_PATH = db_path
        init_db()
        yield mock_config


# ── _payouts_to_odds ─────────────────────────────────────


def test_payouts_to_odds_win() -> None:
    payouts_json = json.dumps({
        "win": [{"combination": "1", "payout": 460}],
        "exacta": [],
        "quinella": [],
        "trifecta": [],
        "trio": [],
        "quinella_place": [],
        "place": [],
    })
    odds = _payouts_to_odds(payouts_json)
    # 460 per 100 yen = 4.6x
    assert odds["win"][1] == 4.6


def test_payouts_to_odds_trifecta() -> None:
    payouts_json = json.dumps({
        "win": [],
        "exacta": [],
        "quinella": [],
        "trifecta": [{"combination": "1-3-2", "payout": 5140}],
        "trio": [],
        "quinella_place": [],
        "place": [],
    })
    odds = _payouts_to_odds(payouts_json)
    assert odds["trifecta"]["1-3-2"] == 51.4


def test_payouts_to_odds_invalid_json() -> None:
    odds = _payouts_to_odds("NOT JSON")
    assert odds == {}


# ── _simulate_old_strategy ───────────────────────────────


def test_simulate_old_strategy_hit() -> None:
    """Old strategy should detect hits with fixed ¥1,000."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.45, 0.20, 0.15, 0.10, 0.06, 0.04]
    payouts_json = json.dumps({
        "win": [{"combination": "1", "payout": 460}],
        "exacta": [],
        "quinella": [],
        "trifecta": [{"combination": "1-3-2", "payout": 5140}],
        "trio": [],
        "quinella_place": [],
        "place": [],
    })

    result = _simulate_old_strategy(order, probs, payouts_json)
    assert result["total_bets"] >= 1
    assert result["total_invested"] == result["total_bets"] * 1000
    # Should hit win (単勝 1) at 460 × 10 = 4600
    assert result["total_payout"] >= 4600


def test_simulate_old_strategy_miss() -> None:
    """Old strategy with no matching payouts."""
    order = [1, 3, 2, 5, 4, 6]
    probs = [0.45, 0.20, 0.15, 0.10, 0.06, 0.04]
    payouts_json = json.dumps({
        "win": [{"combination": "4", "payout": 1500}],
        "exacta": [],
        "quinella": [],
        "trifecta": [],
        "trio": [],
        "quinella_place": [],
        "place": [],
    })

    result = _simulate_old_strategy(order, probs, payouts_json)
    assert result["total_payout"] == 0


# ── _simulate_ev_strategy ────────────────────────────────


def test_simulate_ev_strategy_filters_by_ev() -> None:
    """EV strategy should skip bets with low EV."""
    order = [1, 3, 2, 5, 4, 6]
    # Strong favorite
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    # Low odds → negative EV
    payouts_json = json.dumps({
        "win": [{"combination": "1", "payout": 150}],  # 1.5x odds
        "exacta": [],
        "quinella": [],
        "trifecta": [],
        "trio": [],
        "quinella_place": [],
        "place": [],
    })

    result = _simulate_ev_strategy(order, probs, payouts_json, min_ev=0.20)
    # EV = 0.40 × 1.5 - 1 = -0.4, should be filtered
    assert result["total_bets"] == 0


def test_simulate_ev_strategy_bets_with_edge() -> None:
    """EV strategy should bet when odds provide edge."""
    order = [1, 3, 2, 5, 4, 6]
    probs = {1: 0.40, 3: 0.25, 2: 0.15, 5: 0.10, 4: 0.06, 6: 0.04}
    payouts_json = json.dumps({
        "win": [{"combination": "1", "payout": 400}],  # 4.0x odds, EV = 0.6
        "exacta": [],
        "quinella": [],
        "trifecta": [],
        "trio": [],
        "quinella_place": [],
        "place": [],
    })

    result = _simulate_ev_strategy(order, probs, payouts_json, min_ev=0.20)
    assert result["total_bets"] >= 1
    assert result["total_invested"] > 0


# ── run_backtest ─────────────────────────────────────────


def test_run_backtest_empty() -> None:
    """Backtest with no data returns zeros."""
    result = run_backtest("2026-01-01")
    assert result["old"]["total_bets"] == 0
    assert result["new"]["total_bets"] == 0
    assert result["races_analyzed"] == 0


def test_run_backtest_with_data() -> None:
    """Backtest with DB data produces results."""
    from boatrace_ai.data.models import PredictionResult, RaceResult

    # Save a prediction
    pred = PredictionResult(
        predicted_order=[1, 3, 2, 5, 4, 6],
        confidence=0.65,
        recommended_bets=["単勝 1", "3連単 1-3-2"],
        analysis="test",
    )
    save_prediction("2026-02-28", 1, 1, pred)

    # Save a result with payouts
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
            "trifecta": [{"combination": "1-3-2", "payout": 5140}],
            "trio": [],
            "exacta": [{"combination": "1-3", "payout": 2140}],
            "quinella": [],
            "quinella_place": [],
            "win": [{"combination": "1", "payout": 460}],
            "place": [],
        },
    })
    save_result("2026-02-28", result)

    bt = run_backtest("2026-02-01", "2026-03-01")
    assert bt["races_analyzed"] == 1
    assert bt["old"]["total_bets"] >= 1
    # Old strategy should have hits since prediction matches result
    assert bt["old"]["total_invested"] > 0
