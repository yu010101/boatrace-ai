"""レース後の単勝の確定オッズを集める（2026-10-21 本人OK「シミュレーションの精度をあげたい」）。

目的: 本番の買い方（締切3〜15分前のオッズで判断）と、同じレースを確定オッズで判断した場合の回収率を比べ、
オッズを取る時刻でどれだけ有利が変わるかを測る。本番の予想・本番テスト（10/18〜11/14 事前登録）には何も書かない。

取得は runner.fetch を通す（1日650回の上限・5秒間隔・停止ファイル・取得記録を本番と共有）。
本番が動かない 22時〜翌8時だけ動く。1回に取るのは上限まで余裕 MARGIN を残した分だけ。
  python live/collect_final_odds.py            # 今日の分 → 足りなければ遡って未取得の日
"""
import datetime as dt, json, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner  # noqa: E402
from sources import parse_win_odds  # noqa: E402

MARGIN = 80          # 本番のために残す取得回数
START = dt.date(2026, 10, 18)  # 本番テストの開始日から


def ensure_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS final_win_odds(
        day TEXT, st INTEGER, r INTEGER, odds TEXT, fetched_at TEXT, request_id INTEGER, PRIMARY KEY(day, st, r))""")


def targets(c, primary):
    """本番が締切前に保存したレースのうち、確定オッズをまだ取っていないもの（古い日から）"""
    done = {(d, s, r) for d, s, r in c.execute("SELECT day, st, r FROM final_win_odds")}
    # 2026-10-29: 本番DBは WAL。読み取り専用(mode=ro)だと、他に開いている処理が無い夜は -shm を作れず「unable to open database file」で毎晩止まっていた。
    # 普通に開いて SELECT だけする
    with sqlite3.connect(str(primary)) as p:
        rows = p.execute("SELECT day, st, r, deadline FROM live_v4_predictions WHERE day >= ? ORDER BY day, deadline", (str(START),)).fetchall()
    now = runner.now()
    return [(d, s, r) for d, s, r, dl in rows if (d, s, r) not in done and dt.datetime.fromisoformat(dl) + dt.timedelta(minutes=30) < now]


def main():
    at = runner.now()
    if 8 <= at.hour < 22:
        print("本番の時間帯なので動かない"); return
    config = json.loads((runner.ROOT / "live/config.json").read_text())
    with runner.conn() as c:
        ensure_table(c)
        used = c.execute("SELECT count(*) FROM requests WHERE day=?", (str(at.date()),)).fetchone()[0]
        todo = targets(c, config["primary_db"])
    budget = max(0, 650 - MARGIN - used)
    print(f"取得済み {used} 回、今回の上限 {budget} 回、未取得 {len(todo)} レース", flush=True)
    got = failed = 0
    for d, s, r in todo[:budget]:
        day = dt.date.fromisoformat(d)
        try:
            html, src = runner.fetch(f"https://www.boatrace.jp/owpc/pc/race/oddstf?rno={r}&jcd={s:02d}&hd={day:%Y%m%d}")
            unbet = []
            odds = parse_win_odds(html.decode("utf-8", "replace"), day=d, stadium=s, race_no=r, unbet=unbet)
        except Exception as e:  # 1件の失敗で止めない。403/429 は runner.fetch が1時間止める
            failed += 1
            print("失敗", d, s, r, e, flush=True)
            if "cooldown" in str(e) or "cap" in str(e) or "STOP" in str(e):
                break
            continue
        with runner.conn() as c:
            c.execute("INSERT OR REPLACE INTO final_win_odds VALUES (?,?,?,?,?,?)", (d, s, r, json.dumps({"odds": odds, "unbet": unbet}), src["finished"], src["request_id"]))
        got += 1
    print(f"取得 {got} 件、失敗 {failed} 件", flush=True)


if __name__ == "__main__":
    main()
