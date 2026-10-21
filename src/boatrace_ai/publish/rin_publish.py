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


async def month_ledger(upto: str) -> list[tuple[str, int]]:
    """その月の1日から upto までの、締切前に保存した仮想購入の差引（日ごと）。仮想購入の無い日は飛ばす"""
    d0 = date.fromisoformat(upto).replace(day=1)
    rows = []
    d = d0
    while d.isoformat() <= upto:
        bets = _judged_bets(d.isoformat())
        if bets:
            close = await _closed(d.isoformat())
            if close is not None:
                roi, _ = DL.roi_before_deadline(bets, close)
                if roi["total_bets"]:
                    rows.append((f"{d.month}/{d.day}", roi["total_payout"] - roi["total_invested"]))
        d += timedelta(days=1)
    return rows


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
    top = A.picks(grades, predictions, close)
    dot = race_date.replace("-", ".")
    ledger = await month_ledger(yday)
    pngs = {
        "cover": await V.render(V.cover_html(**A.grades_cover_spec(race_date, grades, top, A.yesterday_line(yesterday))), "cover"),
        "picks": await V.render(V.picks_html(top, f"{dot} ／ %は本命が1着になる見込み。約束ではありません"), "picks") if top else None,
        "ledger": await V.render(V.ledger_html(ledger, f"〜{yday.replace('-', '.')} ／ 締切前に保存した仮想購入だけ。実際に買った舟券ではありません"), "ledger") if ledger else None,
    }
    return {"pngs": pngs, "make": lambda images: A.generate_rin_grades_article(race_date, grades, predictions, yesterday=yesterday, images=images, excluded=excluded, top=top)}


async def build_results(race_date: str, records: list[dict], roi: dict, grades: list[dict]) -> dict:
    """夜の記事の材料。records・roi は締切前に保存したものだけに絞り直す（渡された roi は使わない）"""
    records, roi, excluded = await checked_results(race_date, records)
    close = await _closed(race_date)
    late = _late(race_date, close) if close is not None else set()
    morning = A.picks([g for g in grades if (g["stadium_number"], g["race_number"]) not in late], _pred_map(race_date), close)
    ledger = await month_ledger(race_date)
    inv, pay = roi.get("total_invested", 0), roi.get("total_payout", 0)
    dot = race_date.replace("-", ".")
    pngs: dict[str, Path | None] = {"cover": await V.render(V.cover_html(**A.results_cover_spec(race_date, records, roi)), "cover")}
    if inv:
        lines = [("仮想購入", f"{roi.get('total_bets', 0)}点", V.yen(inv)), ("うち的中", f"{roi.get('hit_count', 0)}点", V.yen(pay))]
        pngs["money"] = await V.render(V.money_html("01 ／ 仮想購入の収支", ["当たった買い目も、", "外れた買い目も足す。"], inv, pay, lines, f"{dot} ／ 実際に買った舟券ではありません"), "money")
    if ledger:
        pngs["ledger"] = await V.render(V.ledger_html(ledger, f"〜{dot} ／ 締切前に保存した仮想購入だけ。実際に買った舟券ではありません"), "ledger")
    rows = A.grade_hit_rows(grades, records)
    if rows:
        pngs["grades"] = await V.render(V.grade_hits_html("02 ／ 推奨度ごとの答え合わせ", ["本命が1着だった数"], rows, f"{dot} ／ 予想と結果がそろったレース"), "grades")
    return {"pngs": pngs, "make": lambda images: A.generate_rin_results_article(race_date, records, roi, grades, images=images, excluded=excluded, morning_picks=morning)}


async def publish(parts: dict, article_type: str, dry_run: bool, preview_dir: Path, new_client) -> dict:
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
    result = await note_client.create_and_publish(title, html_body, price=0, hashtags=hashtags, article_type=article_type, eyecatch_png=pngs.get("cover"))
    result["title"] = title
    return result
