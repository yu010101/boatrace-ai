from boatrace_ai.publish.deadline import before_deadline, parse_close, roi_before_deadline, split_records

CLOSE = {(1, 1): parse_close("2026-10-21 15:26:00"), (1, 2): parse_close("2026-10-21 09:30:00")}


def test_before_deadline_compares_utc_save_with_jst_close():
    assert before_deadline("2026-10-21 00:47:44", CLOSE[(1, 1)])  # 09:47 JST < 15:26
    assert not before_deadline("2026-10-21 00:47:44", CLOSE[(1, 2)])  # 09:47 JST > 09:30
    assert not before_deadline("2026-10-21 00:31:00", CLOSE[(1, 2)])


def test_unknown_close_or_time_is_not_counted():
    assert not before_deadline("2026-10-21 00:00:00", None)
    assert not before_deadline("", CLOSE[(1, 1)])


def test_split_and_roi():
    recs = [{"stadium_number": 1, "race_number": 1}, {"stadium_number": 1, "race_number": 2}]
    made = {(1, 1): "2026-10-21 00:47:44", (1, 2): "2026-10-21 00:47:44"}
    keep, drop = split_records(recs, made, CLOSE)
    assert [r["race_number"] for r in keep] == [1] and [r["race_number"] for r in drop] == [2]
    bets = [
        {"stadium_number": 1, "race_number": 1, "is_hit": 1, "bet_amount": 1000, "payout": 1500, "created_at": "2026-10-21 00:47:44"},
        {"stadium_number": 1, "race_number": 2, "is_hit": 0, "bet_amount": 1000, "payout": 0, "created_at": "2026-10-21 00:47:44"},
        {"stadium_number": 1, "race_number": 1, "is_hit": None, "bet_amount": 1000, "payout": 0, "created_at": "2026-10-21 00:47:44"},
    ]
    roi, dropped = roi_before_deadline(bets, CLOSE)
    assert roi["total_bets"] == 1 and roi["total_invested"] == 1000 and roi["total_payout"] == 1500 and dropped == 1
