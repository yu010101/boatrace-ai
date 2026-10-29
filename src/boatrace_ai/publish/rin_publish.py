"""りんの毎日の記事を、図づくり → note へ画像を上げる → 本文 → 見出し画像つきで公開、の順に出す（2026-10-21）。

cli の publish grades / publish results から呼ぶ。dry_run では公開せず、本文の HTML と画像を out_dir に書き出す。
"""

from __future__ import annotations

import logging
import shutil
import struct
from datetime import date, timedelta
from pathlib import Path

from boatrace_ai.publish import deadline as DL
from boatrace_ai.publish import rin_article as A
from boatrace_ai.publish import rin_visuals as V

log = logging.getLogger(__name__)


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    return struct.unpack(">II", head[16:24])


async def _upload_all(note_client, pngs: dict[str, Path | None]) -> dict[str, tuple[str, int, int]]:
    out: dict[str, tuple[str, int, int]] = {}
    for key, path in pngs.items():
        if not path:
            continue
        try:
            url = await note_client.upload_image(path)
            w, h = _png_size(path)
            out[key] = (url, w, h)
        except Exception as e:
            log.warning("図 %s を上げられなかった（図なしで続ける）: %s", key, e)
    return out


def _write_preview(out_dir: Path, title: str, html_body: str, pngs: dict[str, Path | None]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, path in pngs.items():
        if path:
            shutil.copy(path, out_dir / f"{key}.png")
    page = out_dir / "preview.html"
    page.write_text(f"<!doctype html><meta charset=utf-8><title>{title}</title><body style='max-width:620px;margin:24px auto;font-family:sans-serif;line-height:1.9'><h1>{title}</h1>{html_body}</body>", encoding="utf-8")
    return page


def _made_at(race_date: str) -> dict[tuple[int, int], str]:
    from boatrace_ai.storage.database import get_predictions_for_date
    return {(p["stadium_number"], p["race_number"]): p["created_at"] for p in get_predictions_for_date(race_date)}


def _judged_bets(race_date: str) -> list[dict]:
    from boatrace_ai.storage.database import _get_connection
    conn = _get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM virtual_bets WHERE race_date = ? AND is_hit IS NOT NULL", (race_date,)).fetchall()]
    finally:
        conn.close()


CLOSE_CACHE = Path.home() / ".boatrace-ai" / "close_cache"


async def _closed(race_date: str) -> dict | None:
    """締切の一覧。終わった日の分はファイルに控えて使い回す（答え合わせ帳で毎日ひと月分を引くため）"""
    import json
    from datetime import datetime
    cache = CLOSE_CACHE / f"{race_date}.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
        return {(int(k.split("-")[0]), int(k.split("-")[1])): datetime.fromisoformat(v) for k, v in raw.items()}
    try:
        m = await DL.closed_map(race_date)
    except Exception as e:
        log.warning("締切を取れなかった（%s）: %s", race_date, e)
        return None
    if m and race_date < date.today().isoformat():
        CLOSE_CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({f"{k[0]}-{k[1]}": v.isoformat() for k, v in m.items()}))
    return m


async def month_ledger(upto: str) -> list[tuple[str, int, int]]:
    """その月の1日から upto までの、締切前に保存した予想の (日付, 本命が1着だった数, レース数)。
    2026-10-21 本人OK: 答え合わせ帳は仮想購入の差引ではなく本命の的中率で見せる（差引は旧い買い方で今月 −43万円。新しい買い方は 10/18〜11/14 の本番テスト中）"""
    from boatrace_ai.storage.database import get_accuracy_for_date
    d0 = date.fromisoformat(upto).replace(day=1)
    rows = []
    d = d0
    while d.isoformat() <= upto:
        recs = get_accuracy_for_date(d.isoformat())
        if recs:
            close = await _closed(d.isoformat())
            if close is not None:
                keep, _ = DL.split_records(recs, _made_at(d.isoformat()), close)
                if keep:
                    rows.append((f"{d.month}/{d.day}", sum(1 for r in keep if r["hit_1st"]), len(keep)))
        d += timedelta(days=1)
    return rows


PUBLISH_MARGIN = timedelta(minutes=15)


def _picks_file(race_date: str) -> Path:
    from boatrace_ai import config
    return Path(config.DB_PATH).parent / "rin_picks" / f"{race_date}.json"


def save_picks(race_date: str, top: list[dict]) -> None:
    """朝に選んだ勝負レースを控える（DB と同じ場所＝Actions のキャッシュに載る）。夜はこれを読んで同じレースを答え合わせする"""
    import json
    f = _picks_file(race_date)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(top, ensure_ascii=False))


def load_picks(race_date: str) -> list[dict] | None:
    import json
    f = _picks_file(race_date)
    return json.loads(f.read_text()) if f.exists() else None


def open_after():
    """記事を出す時刻＋余裕。これより前に締め切るレースは勝負レースに選ばない"""
    from datetime import datetime
    return datetime.now(DL.JST) + PUBLISH_MARGIN


CALIB_DAYS = 30


async def calibration(upto: str, days: int = CALIB_DAYS) -> dict | None:
    """upto までの days 日、締切前に保存した予想について、見込みの帯ごとの (本命が1着だった数, レース数)"""
    from boatrace_ai.storage.database import get_accuracy_for_date, get_grades_for_date
    bands: dict[str, list[int]] = {}
    seen = []
    d = date.fromisoformat(upto) - timedelta(days=days - 1)
    while d.isoformat() <= upto:
        ds = d.isoformat()
        d += timedelta(days=1)
        recs = get_accuracy_for_date(ds)
        if not recs:
            continue
        close = await _closed(ds)
        if close is None:
            continue
        keep, _ = DL.split_records(recs, _made_at(ds), close)
        prob = {(g["stadium_number"], g["race_number"]): g["top1_prob"] for g in get_grades_for_date(ds)}
        used = False
        for r in keep:
            pr = prob.get((r["stadium_number"], r["race_number"]))
            if pr is None:
                continue
            b = bands.setdefault(A.calib_band(round(pr * 100)), [0, 0])
            b[0] += 1 if r["hit_1st"] else 0
            b[1] += 1
            used = True
        if used:
            seen.append(ds)
    if not seen:
        return None
    return {"from": seen[0], "to": seen[-1], "days": len(seen), "bands": {k: tuple(v) for k, v in bands.items()}}


async def safe_calibration(upto: str) -> dict | None:
    """実績の集計に失敗しても記事は出す（その段落を出さないだけ）"""
    try:
        return await calibration(upto)
    except Exception as e:
        log.warning("見込みの実績を集計できなかった（%s）: %s", upto, e)
        return None


def calib_rows(calib: dict) -> list[tuple[str, int, int]]:
    return [(f"見込み{label}", *calib["bands"][label]) for _, _, label in A.CALIB_BANDS if label in calib["bands"]]


def _late(race_date: str, close: dict) -> set:
    made = _made_at(race_date)
    return {k for k in made if not DL.before_deadline(made[k], close.get(k))}


def _pred_map(race_date: str) -> dict:
    import json
    from boatrace_ai.storage.database import get_predictions_for_date
    out = {}
    for p in get_predictions_for_date(race_date):
        try:
            out[(p["stadium_number"], p["race_number"])] = json.loads(p["predicted_order"]) if isinstance(p["predicted_order"], str) else p["predicted_order"]
        except (TypeError, ValueError):
            pass
    return out


async def checked_results(race_date: str, records: list[dict]) -> tuple[list[dict], dict, dict | None]:
    """締切前に保存したものだけの (答え合わせ行, 収支, 外した件数)。締切が取れなければ全件と None"""
    from boatrace_ai.storage.database import get_roi_daily
    close = await _closed(race_date)
    if close is None:
        return records, get_roi_daily(race_date), None
    keep, drop = DL.split_records(records, _made_at(race_date), close)
    roi, dropped_bets = DL.roi_before_deadline(_judged_bets(race_date), close)
    return keep, roi, {"races": len(drop), "bets": dropped_bets}


async def build_grades(race_date: str, grades: list[dict], predictions: dict, get_accuracy_for_date, get_roi_daily) -> dict:
    """朝の記事の材料（画像の PNG と、画像URLを受けて本文を作る関数）"""
    yday = (date.fromisoformat(race_date) - timedelta(days=1)).isoformat()
    y_records, y_roi, _ = await checked_results(yday, get_accuracy_for_date(yday))
    yesterday = {"date": yday, "records": y_records, "roi": y_roi}
    close = await _closed(race_date)
    excluded = None
    if close is not None:
        late = _late(race_date, close)
        grades = [g for g in grades if (g["stadium_number"], g["race_number"]) not in late]
        excluded = {"races": len(late)}
    top = A.picks(grades, predictions, close, after=open_after() if race_date == date.today().isoformat() else None)
    dot = race_date.replace("-", ".")
    ledger = await month_ledger(yday)
    calib = await safe_calibration(yday)
    pngs = {
        "cover": await V.render(V.cover_html(**A.grades_cover_spec(race_date, grades, top, A.yesterday_line(yesterday))), "cover"),
        "picks": await V.render(V.picks_html(top, f"{dot} ／ %は本命が1着になる見込み。約束ではありません"), "picks") if top else None,
        "ledger": await V.render(V.ledger_html(ledger, f"〜{yday.replace('-', '.')} ／ 締切前に保存した予想だけ。本命＝1着になる見込みがいちばん高い艇"), "ledger") if ledger else None,
        "calib": await V.render(V.grade_hits_html(f"見込みの答え合わせ ／ {A._date_short(calib['from'])}〜{A._date_short(calib['to'])}", ["見込みごとに、", "本命が1着だった数"], calib_rows(calib), f"〜{yday.replace('-', '.')} ／ 締切前に保存した予想だけ"), "calib") if calib else None,
    }
    return {"pngs": pngs, "top": top, "make": lambda images: A.generate_rin_grades_article(race_date, grades, predictions, yesterday=yesterday, images=images, excluded=excluded, top=top, calib=calib)}


async def build_results(race_date: str, records: list[dict], roi: dict, grades: list[dict]) -> dict:
    """夜の記事の材料。records・roi は締切前に保存したものだけに絞り直す（渡された roi は使わない）"""
    records, roi, excluded = await checked_results(race_date, records)
    close = await _closed(race_date)
    late = _late(race_date, close) if close is not None else set()
    morning = load_picks(race_date)
    if morning is None:
        morning = A.picks([g for g in grades if (g["stadium_number"], g["race_number"]) not in late], _pred_map(race_date), close)
    ledger = await month_ledger(race_date)
    inv, pay = roi.get("total_invested", 0), roi.get("total_payout", 0)
    dot = race_date.replace("-", ".")
    pngs: dict[str, Path | None] = {"cover": await V.render(V.cover_html(**A.results_cover_spec(race_date, records, roi)), "cover")}
    if inv:
        lines = [("仮想購入", f"{roi.get('total_bets', 0)}点", V.yen(inv)), ("うち的中", f"{roi.get('hit_count', 0)}点", V.yen(pay))]
        pngs["money"] = await V.render(V.money_html("01 ／ 仮想購入の収支", ["当たった買い目も、", "外れた買い目も足す。"], inv, pay, lines, f"{dot} ／ 実際に買った舟券ではありません"), "money")
    if ledger:
        pngs["ledger"] = await V.render(V.ledger_html(ledger, f"〜{dot} ／ 締切前に保存した予想だけ。本命＝1着になる見込みがいちばん高い艇"), "ledger")
    rows = A.grade_hit_rows(grades, records)
    if rows:
        pngs["grades"] = await V.render(V.grade_hits_html("02 ／ 推奨度ごとの答え合わせ", ["本命が1着だった数"], rows, f"{dot} ／ 予想と結果がそろったレース"), "grades")
    return {"pngs": pngs, "make": lambda images: A.generate_rin_results_article(race_date, records, roi, grades, images=images, excluded=excluded, morning_picks=morning)}


async def build_race(race, prediction, grade: dict, free: bool = True) -> dict:
    """推奨度Sの1レースの記事の材料（旧 premium）"""
    close = await _closed(race.race_date)
    c = (close or {}).get((race.race_stadium_number, race.race_number))
    venue = A.STADIUMS.get(race.race_stadium_number, str(race.race_stadium_number))
    order = list(prediction.predicted_order)
    pct = round(grade["top1_prob"] * 100)
    top = [{"st": race.race_stadium_number, "venue": venue, "race": race.race_number, "order": order[:3], "pct": pct, "close": c.strftime("%H:%M") if c else ""}]
    dot = race.race_date.replace("-", ".")
    calib = await safe_calibration((date.fromisoformat(race.race_date) - timedelta(days=1)).isoformat())
    pngs = {
        "cover": await V.render(V.cover_html(**A.race_cover_spec(race.race_date, venue, race.race_number, order, pct)), "cover"),
        "picks": await V.render(V.picks_html(top, f"{dot} ／ %は本命が1着になる見込み。約束ではありません"), "picks"),
        "calib": await V.render(V.grade_hits_html(f"見込みの答え合わせ ／ {A._date_short(calib['from'])}〜{A._date_short(calib['to'])}", ["見込みごとに、", "本命が1着だった数"], calib_rows(calib), "締切前に保存した予想だけ"), "calib") if calib else None,
    }
    def make(images):
        title, html, tags = A.generate_rin_race_article(race, prediction, grade, top[0]["close"], free, calib=calib)
        fig = A._figure(images.get("picks"), "りんの予想（本命・対抗・3着候補と、本命が1着になる見込み）")
        html = html.replace("<h2>りんの予想</h2>", "<h2>りんの予想</h2>\n" + fig, 1) if fig else html
        cf = A._figure(images.get("calib"), "見込みの帯ごとの、本命が1着だった数とレース数")
        return title, html.replace("<h2>この見込み、これまでどうだった？</h2>", "<h2>この見込み、これまでどうだった？</h2>\n" + cf, 1) if cf else html, tags
    return {"pngs": pngs, "make": make}


async def build_midday(race_date: str, records: list[dict], grades: list[dict]) -> dict:
    """昼の途中経過の材料（旧 midday）。records は結果が出たレースだけ"""
    close = await _closed(race_date)
    excluded = None
    if close is not None:
        records, drop = DL.split_records(records, _made_at(race_date), close)
        excluded = {"races": len(drop), "bets": 0}
    late = _late(race_date, close) if close is not None else set()
    morning = A.picks([g for g in grades if (g["stadium_number"], g["race_number"]) not in late], _pred_map(race_date), close)
    dot = race_date.replace("-", ".")
    pngs: dict[str, Path | None] = {"cover": await V.render(V.cover_html(**A.midday_cover_spec(race_date, records)), "cover")}
    rows = A.grade_hit_rows(grades, records)
    if rows:
        pngs["grades"] = await V.render(V.grade_hits_html("ここまでの途中経過", ["推奨度ごとの", "本命が1着だった数"], rows, f"{dot} ／ 結果が出たレースだけ"), "grades")
    return {"pngs": pngs, "make": lambda images: A.generate_rin_midday_article(race_date, records, grades, images=images, excluded=excluded, morning_picks=morning)}


async def build_hit(race_date: str, records: list[dict], min_payout: int) -> dict | None:
    """高配当の速報の材料（旧 hit-flash）。締切前に保存した予想の一致だけで選ぶ。無ければ None"""
    records, _, excluded = await checked_results(race_date, records)
    big = [r for r in records if r["hit_trifecta"] and int(r.get("trifecta_payout") or 0) >= min_payout]
    if not big:
        return None
    best = max(big, key=lambda r: int(r["trifecta_payout"]))
    ledger = await month_ledger(race_date)
    pngs: dict[str, Path | None] = {"cover": await V.render(V.cover_html(**A.hit_cover_spec(race_date, best, records)), "cover")}
    if ledger:
        pngs["ledger"] = await V.render(V.ledger_html(ledger, f"〜{race_date.replace('-', '.')} ／ 締切前に保存した予想だけ"), "ledger")
    return {"pngs": pngs, "make": lambda images: A.generate_rin_hit_article(race_date, best, records, images=images, excluded=excluded), "best": best}


async def span_days(upto: str, days: int) -> list[dict]:
    """upto までの days 日の、締切前に保存したものだけの日ごとの数字（古い順）。締切が取れない日は入れない"""
    from boatrace_ai.storage.database import get_accuracy_for_date
    out = []
    for i in range(days - 1, -1, -1):
        d = (date.fromisoformat(upto) - timedelta(days=i)).isoformat()
        recs = get_accuracy_for_date(d)
        if not recs or await _closed(d) is None:
            continue
        keep, roi, exc = await checked_results(d, recs)
        if keep:
            out.append({"date": d, "hit": sum(1 for r in keep if r["hit_1st"]), "n": len(keep), "tri": sum(1 for r in keep if r["hit_trifecta"]),
                        "inv": roi.get("total_invested", 0), "pay": roi.get("total_payout", 0),
                        "dropped_races": (exc or {}).get("races", 0), "dropped_bets": (exc or {}).get("bets", 0)})
    return out


async def build_span(upto: str, days: int, label: str, paid: bool = False) -> dict | None:
    """期間のまとめの材料（旧 track-record・weekly-premium）"""
    rows = await span_days(upto, days)
    if not rows:
        return None
    if len(rows) < days:
        # 締切と照合できない日は入れないので、題名と図には実際に数えた日数を書く（2026-10-28: 30日のうち23日だった）
        label = f"{A._date_short(rows[0]['date'])}〜{A._date_short(rows[-1]['date'])}の{len(rows)}日"
    ledger = [(f"{int(r['date'][5:7])}/{int(r['date'][8:10])}", r["hit"], r["n"]) for r in rows]
    pngs = {
        "cover": await V.render(V.cover_html(**A.span_cover_spec(rows, label)), "cover"),
        "ledger": await V.render(V.ledger_html(ledger, f"{rows[0]['date'].replace('-', '.')}〜{upto.replace('-', '.')} ／ 締切前に保存した予想だけ", period=label), "ledger"),
    }
    return {"pngs": pngs, "make": lambda images: A.generate_rin_span_article(rows, label, images=images, paid=paid)}


def _results_since(since: str, upto: str) -> list[dict]:
    """results から 1着の艇と3連単の払戻。結果が無い・読めないレースは入れない"""
    import json
    from boatrace_ai.storage.database import _get_connection
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT stadium_number, actual_order, payouts_json FROM results WHERE race_date BETWEEN ? AND ?", (since, upto)).fetchall()
    finally:
        conn.close()
    out = []
    for st, order, pj in rows:
        try:
            first = json.loads(order)[0]
            tri = (json.loads(pj or "{}").get("trifecta") or [{}])[0].get("payout")
        except (TypeError, ValueError, IndexError):
            continue
        if first:
            out.append({"stadium_number": st, "first": int(first), "trifecta_payout": tri})
    return out


async def build_venues(upto: str, days: int = 90) -> dict | None:
    """場ごとの1号艇の勝ちやすさの材料（週1回）"""
    since = (date.fromisoformat(upto) - timedelta(days=days - 1)).isoformat()
    res = _results_since(since, upto)
    if not res:
        return None
    rows = A.venue_rows(res)
    label = f"{A._date_short(since)}〜{A._date_short(upto)}"
    gr = [(v["venue"], v["boat1"], v["n"]) for v in rows]
    pngs = {
        "cover": await V.render(V.cover_html(**A.venue_cover_spec(rows, label)), "cover"),
        "venues": await V.render(V.grade_hits_html("場ごとの1号艇", ["1号艇が1着だった数"], gr, f"{label} ／ 公式の結果。中止・結果なしは数えていません"), "venues"),
    }
    return {"pngs": pngs, "make": lambda images: A.generate_rin_venue_article(rows, label, images=images)}


async def publish(parts: dict, article_type: str, dry_run: bool, preview_dir: Path, new_client, price: int = 0) -> dict:
    """parts は build_* の戻り値。dry_run なら preview_dir に書き出して終わる"""
    pngs = parts["pngs"]
    if dry_run:
        local = {k: (str((preview_dir / f"{k}.png").name), *_png_size(p)) for k, p in pngs.items() if p and k != "cover"}
        title, html_body, hashtags = parts["make"](local)
        page = _write_preview(preview_dir, title, html_body, pngs)
        return {"title": title, "preview": str(page), "hashtags": hashtags}
    note_client = new_client()
    await note_client.ensure_logged_in()
    images = await _upload_all(note_client, {k: p for k, p in pngs.items() if k != "cover"})
    title, html_body, hashtags = parts["make"](images)
    result = await note_client.create_and_publish(title, html_body, price=price, hashtags=hashtags, article_type=article_type, eyecatch_png=pngs.get("cover"))
    result["title"] = title
    return result
