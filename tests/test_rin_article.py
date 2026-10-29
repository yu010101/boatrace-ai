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


# ── 2026-10-28 旧型5種類のりん版 ──
from types import SimpleNamespace

from boatrace_ai.publish.rin_article import (
    generate_rin_hit_article, generate_rin_midday_article, generate_rin_race_article, generate_rin_span_article,
)

OLD_MARKS = ("水理", "━━", "◆", "AI詳細分析")


def _boat(n):
    return SimpleNamespace(racer_boat_number=n, racer_name=f"選手{n}", racer_class_number=1, racer_average_start_timing=0.15,
                           racer_national_top_1_percent=6.5, racer_local_top_1_percent=6.1,
                           racer_assigned_motor_top_2_percent=40.0, racer_assigned_boat_top_2_percent=35.0)


def test_race_article_is_rin_style_and_has_no_llm_analysis():
    race = SimpleNamespace(race_stadium_number=1, race_number=5, race_date="2026-10-28", boats=[_boat(i) for i in range(1, 7)])
    pred = SimpleNamespace(predicted_order=[1, 3, 2, 4, 5, 6], confidence=0.9, recommended_bets=["3連単 1-3-2"], analysis="AIの分析では展開が向く")
    title, html, _ = generate_rin_race_article(race, pred, {"top1_prob": 0.79}, "11:09", free=True)
    assert "AI" not in title and "本命1号艇・見込み79%" in title
    assert "展開が向く" not in html and all(m not in html for m in OLD_MARKS)
    assert "<pay>" not in html and "選手3" in html and "1 → 3 → 2" in html
    _, paid, _ = generate_rin_race_article(race, pred, {"top1_prob": 0.79}, free=False)
    assert "<pay>" in paid


def test_midday_counts_and_pending_picks():
    mp = picks(GR, {(1, 1): [1, 2, 3]})
    title, html, _ = generate_rin_midday_article("2026-10-28", REC[:1], GR, morning_picks=mp + [{"st": 9, "venue": "津", "race": 1, "order": [1], "pct": 50, "close": ""}])
    assert "午前の答え合わせ｜本命1/1的中" in title and "AI" not in title
    assert "まだ結果が出ていません" in html and all(m not in html for m in OLD_MARKS)


def test_hit_article_shows_the_whole_day():
    title, html, _ = generate_rin_hit_article("2026-10-20", REC[0], REC)
    assert "3連単1,010円が予想どおり" in title and "AI" not in title
    assert "2レース中1レース" in html and "実際に買った舟券ではありません" in html


def test_span_article_sums_days_and_paywall():
    days = [{"date": "2026-10-20", "hit": 3, "n": 5, "tri": 1, "inv": 1000, "pay": 400, "dropped_races": 2, "dropped_bets": 4},
            {"date": "2026-10-21", "hit": 2, "n": 5, "tri": 0, "inv": 1000, "pay": 1200}]
    title, html, _ = generate_rin_span_article(days, "直近2日")
    assert "本命5/10的中（50%）・3連単1本" in title and "AI" not in title
    assert "差引−400円" in html and "締切後に保存された予想2レースと仮想購入4点" in html and "<pay>" not in html
    _, paid, _ = generate_rin_span_article(days, "この1週間", paid=True)
    assert "<pay>" in paid
