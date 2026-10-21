from boatrace_ai.publish.rin_article import _jst_hm, generate_rin_grades_article, generate_rin_results_article, grade_hit_rows, picks

GR = [
    {"stadium_number": 1, "race_number": 1, "grade": "S", "top1_prob": 0.6, "created_at": "2026-10-21 00:47:44"},
    {"stadium_number": 1, "race_number": 2, "grade": "A", "top1_prob": 0.35, "created_at": "2026-10-21 00:50:00"},
]
REC = [
    {"stadium_number": 1, "race_number": 1, "hit_1st": True, "hit_trifecta": True, "actual_trifecta": "1-2-3", "trifecta_payout": 1010},
    {"stadium_number": 1, "race_number": 2, "hit_1st": False, "hit_trifecta": False, "actual_trifecta": "4-5-1", "trifecta_payout": 0},
]
ROI = {"total_bets": 2, "total_invested": 2000, "total_payout": 1300, "hit_count": 1}


def test_jst():
    assert _jst_hm("2026-10-21 00:47:44") == "09:47"


def test_grade_hit_rows():
    assert grade_hit_rows(GR, REC) == [("推奨度S", 1, 1), ("推奨度A", 0, 1)]


def test_results_article_lists_all_and_no_old_brand():
    title, html, tags = generate_rin_results_article("2026-10-20", REC, ROI, GR)
    assert "本命1/2的中" in title and "3連単1本ズバリ" in title and "AI" not in title
    assert "水理" not in html and "━━" not in html and "◆" not in html
    assert "差引−700円" in html
    assert "桐生 1R" in html  # 一致した3連単は全部載せる
    assert "実際に買った舟券ではありません" in html


def test_grades_article_has_times_and_rules():
    title, html, tags = generate_rin_grades_article("2026-10-21", GR, {(1, 1): [1, 2, 3], (1, 2): [2, 1, 3]}, yesterday={"date": "2026-10-20", "records": REC, "roi": ROI})
    assert "勝負レース1選" in title and "昨日は本命1/2的中" in title and "AI" not in title
    assert "09:47〜09:50" in html
    assert "朝の時点で結果がそろった2レース" in html
    assert "◎1 ○2 △3" in html
    assert "水理" not in html and "7:30" not in html


def test_picks_one_per_venue_by_highest_chance():
    gr = GR + [{"stadium_number": 1, "race_number": 3, "grade": "S", "top1_prob": 0.9, "created_at": ""},
               {"stadium_number": 2, "race_number": 1, "grade": "S", "top1_prob": 0.5, "created_at": ""}]
    top = picks(gr, {(1, 3): [1, 2, 3], (2, 1): [3, 1, 2]})
    assert [(t["st"], t["race"], t["pct"]) for t in top] == [(1, 3, 90), (2, 1, 50)]


def test_results_shows_morning_picks_outcome():
    mp = picks(GR, {(1, 1): [1, 2, 3]})
    _, html, _ = generate_rin_results_article("2026-10-20", REC, ROI, GR, morning_picks=mp)
    assert "朝の勝負レース3選、結果は？" in html and "的中！" in html


def test_ledger_shows_monthly_hit_rate_not_money():
    from boatrace_ai.publish.rin_visuals import ledger_html
    h = ledger_html([("10/19", 70, 130), ("10/20", 83, 144)], "foot")
    assert "本命の的中率、今月は" in h and "56%" in h and "274レース中 153レース" in h and "円" not in h
