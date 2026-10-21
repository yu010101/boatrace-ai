"""りん（競艇データバンク）の記事用の画像。見出し画像と図を HTML から Playwright で書き出す。

組み方は 10/16 に作った答え合わせの見本（~/tasks/kyotei-db-20261015/drafts/note_brand/visuals/layout.html）と同じ。
色: 濃い緑 #183638（文字・購入額）、緑 #17766e（払戻・強調）、赤茶 #a34432（マイナス）、地 #f8f6ef / #eaf3ec。
数字はすべて呼び出し元が DB から渡す。ここでは作らない。
"""

from __future__ import annotations

import base64
import html
import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

RIN_IMAGE = Path(__file__).parent / "assets" / "rin_cutout_v4.png"

_CSS = """
*{box-sizing:border-box}body{margin:0;font-family:'Hiragino Kaku Gothic ProN','Hiragino Sans',sans-serif;color:#183638}
.asset{position:relative;width:1280px;overflow:hidden;background:#f8f6ef;padding:64px}
small{font-size:24px;letter-spacing:.05em}h1,h2,p{margin:0}h1{font-size:66px;line-height:1.4;letter-spacing:-2px}h2{font-size:52px;line-height:1.5}
strong{font-weight:800}.tag{font-size:26px;background:#183638;color:#fff;display:inline-block;padding:8px 18px}
.sub{font-size:30px;line-height:1.6}.foot{margin-top:44px;font-size:24px;color:#455d5e}#cover .foot{position:absolute;bottom:35px;left:64px;margin:0}
.teal{color:#17766e}.minus{color:#a34432}
#cover{height:670px;background:#eaf3ec}#cover:after{content:'';position:absolute;width:580px;height:580px;border-radius:50%;right:-45px;top:65px;background:#cde6de}
#cover img{position:absolute;height:900px;width:auto;right:-70px;top:25px;z-index:1}#cover .copy{position:relative;z-index:2;width:780px}
#cover h1{margin-top:35px;font-size:58px}#cover .amount{font-size:60px;letter-spacing:-2px;white-space:nowrap;margin-top:26px}
.label{font-size:30px;margin:32px 0 12px}.bar{height:95px;background:#183638;color:#fff;display:flex;align-items:center;padding-left:25px;font-size:45px;font-weight:700;white-space:nowrap}
.bar.return{background:#17766e}.net{margin-top:34px;padding:20px 0;border-top:2px solid #b7c4bf;font-size:38px}
.line{font-size:30px;display:flex;justify-content:space-between;border-bottom:1px solid #cdd8d3;padding:15px 0}.line em{font-style:normal;color:#536968;font-size:25px}
.gbar{height:56px;background:#17766e;display:inline-block;vertical-align:middle}.gbar.miss{background:#cdd8d3}
.grow{display:grid;grid-template-columns:150px 1fr 300px;align-items:center;gap:20px;font-size:32px;padding:14px 0;border-bottom:1px solid #cdd8d3}
"""


def _img_data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def yen(n: int) -> str:
    return f"{n:,}円"


def cover_html(tag: str, headline: list[str], amount_html: str, sub: list[str], foot: str) -> str:
    """見出し画像（1280x670）。headline・sub は1行ずつ。amount_html だけは呼び出し元で組んだ HTML（数字の強調用）"""
    img = f'<img src="{_img_data_uri(RIN_IMAGE)}" alt="りん">' if RIN_IMAGE.exists() else ""
    return (
        f'<section class="asset" id="cover"><div class="copy"><div class="tag">{_e(tag)}</div>'
        f'<h1>{"<br>".join(_e(h) for h in headline)}</h1>'
        f'<p class="amount">{amount_html}</p>'
        f'<p class="sub" style="margin-top:22px">{"<br>".join(_e(s) for s in sub)}</p></div>'
        f'{img}<div class="foot" style="z-index:3">{_e(foot)}</div></section>'
    )


def money_html(kicker: str, headline: list[str], invested: int, payout: int, lines: list[tuple[str, str, str]], foot: str) -> str:
    """購入額と払戻額を同じ物差しの横棒で並べる図（YNAB の「合計→内訳」の型）。lines は (左, 左の補足, 右)"""
    top = max(invested, payout, 1)
    w_inv = max(invested / top * 100, 18)
    w_pay = max(payout / top * 100, 18) if payout else 0
    net = payout - invested
    net_cls = "minus" if net < 0 else "teal"
    net_txt = ("−" if net < 0 else "+") + yen(abs(net))
    rows = "".join(f'<div class="line"><span>{_e(a)} <em>{_e(b)}</em></span><strong>{_e(c)}</strong></div>' for a, b, c in lines)
    pay_bar = f'<div class="bar return" style="width:{w_pay:.1f}%">{yen(payout)}</div>' if payout else '<div class="bar return" style="width:18%;background:#cdd8d3;color:#183638">0円</div>'
    return (
        f'<section class="asset"><small>{_e(kicker)}</small>'
        f'<h2 style="margin-top:20px">{"<br>".join(_e(h) for h in headline)}</h2>'
        f'<div class="label">仮想購入額</div><div class="bar" style="width:{w_inv:.1f}%">{yen(invested)}</div>'
        f'<div class="label">仮想払戻額</div>{pay_bar}'
        f'<div class="net">差引　<strong class="{net_cls}">{net_txt}</strong></div>{rows}'
        f'<div class="foot">{_e(foot)}</div></section>'
    )


def grade_hits_html(kicker: str, headline: list[str], rows: list[tuple[str, int, int]], foot: str) -> str:
    """推奨度ごとの「本命が1着だった数／レース数」。rows は (ラベル, 一致数, レース数)"""
    body = []
    for label, hit, n in rows:
        pct = hit / n * 100 if n else 0
        body.append(
            f'<div class="grow"><strong>{_e(label)}</strong>'
            f'<div><span class="gbar" style="width:{pct * 0.8:.1f}%"></span><span class="gbar miss" style="width:{(100 - pct) * 0.8:.1f}%"></span></div>'
            f'<span style="text-align:right">{hit} / {n}（{round(pct)}%）</span></div>'
        )
    return (
        f'<section class="asset"><small>{_e(kicker)}</small>'
        f'<h2 style="margin-top:20px;margin-bottom:24px">{"<br>".join(_e(h) for h in headline)}</h2>'
        f'{"".join(body)}<div class="foot">{_e(foot)}</div></section>'
    )


async def render(section_html: str, name: str) -> Path | None:
    """section を1枚の PNG にする。失敗したら None（記事は画像なしで続ける）"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("playwright が無いため画像を作らない")
        return None
    tmp = Path(tempfile.mkdtemp(prefix="rin_"))
    page_path = tmp / f"{name}.html"
    png_path = tmp / f"{name}.png"
    page_path.write_text(f"<!doctype html><html lang=ja><meta charset=utf-8><style>{_CSS}</style>{section_html}</html>", encoding="utf-8")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 900})
                await page.goto(f"file://{page_path}")
                await page.evaluate("document.fonts.ready")
                await page.locator("section").screenshot(path=str(png_path))
                return png_path
            finally:
                await browser.close()
    except Exception as e:
        log.error("りんの画像を作れなかった (%s): %s", name, e)
        return None


# 艇番の色（1白・2黒・3赤・4青・5黄・6緑）。文字色は読めるほうに
BOAT_COLORS = {1: ("#ffffff", "#183638"), 2: ("#1d1d1d", "#ffffff"), 3: ("#d93a32", "#ffffff"), 4: ("#2459c7", "#ffffff"), 5: ("#f2c418", "#183638"), 6: ("#1f9a50", "#ffffff")}
_PICK_CSS = (
    ".pick{display:grid;grid-template-columns:260px 1fr 190px;align-items:center;gap:24px;background:#fff;border:2px solid #cdd8d3;padding:26px 30px;margin-top:22px}"
    ".pick .where{font-size:46px;font-weight:800;line-height:1.2}.pick .where em{display:block;font-style:normal;font-size:26px;font-weight:400;color:#536968;margin-top:6px}"
    ".boats{display:flex;gap:14px;align-items:flex-end}.boat{width:92px;text-align:center}.boat i{display:block;font-style:normal;font-size:24px;color:#536968;margin-bottom:6px}"
    ".boat b{display:block;font-size:50px;line-height:84px;border:2px solid #183638}"
    ".pct{text-align:right;font-size:28px;color:#536968}.pct strong{display:block;font-size:64px;color:#17766e;letter-spacing:-2px}"
    ".ledger{display:flex;align-items:center;gap:6px;height:360px;margin-top:30px;position:relative;border-bottom:2px solid #b7c4bf}"
    ".lcol{flex:1;display:flex;flex-direction:column;justify-content:center;height:100%;position:relative}"
    ".lbar{position:absolute;left:10%;width:80%}.lbar.plus{background:#17766e}.lbar.minus{background:#a34432}"
    ".lday{position:absolute;bottom:-34px;width:100%;text-align:center;font-size:20px;color:#536968}"
)


def picks_html(top: list[dict], foot: str) -> str:
    """勝負レースのカード。top は rin_article.picks() の戻り値"""
    cards = []
    for t in top:
        boats = []
        for mark, b in zip(["本命", "対抗", "3着"], t["order"]):
            bg, fg = BOAT_COLORS.get(int(b), ("#fff", "#183638"))
            boats.append(f'<div class="boat"><i>{mark}</i><b style="background:{bg};color:{fg}">{int(b)}</b></div>')
        close = f"締切 {_e(t['close'])}" if t.get("close") else ""
        cards.append(
            f'<div class="pick"><div class="where">{_e(t["venue"])} {t["race"]}R<em>{close}</em></div>'
            f'<div class="boats">{"".join(boats)}</div>'
            f'<div class="pct">1着の見込み<strong>{t["pct"]}%</strong></div></div>'
        )
    return (
        f'<style>{_PICK_CSS}</style><section class="asset"><div class="tag">りんの勝負レース</div>'
        f'<h2 style="margin-top:26px">今日はこの{len(top)}レース！</h2>{"".join(cards)}'
        f'<div class="foot">{_e(foot)}</div></section>'
    )


def ledger_html(rows: list[tuple[str, int]], foot: str) -> str:
    """今月の答え合わせ帳。rows は (日付 "10/20", その日の差引)。棒は累計の差引"""
    cum, acc = [], 0
    for d, net in rows:
        acc += net
        cum.append((d, acc))
    top = max([abs(v) for _, v in cum] + [1])
    cols = []
    for d, v in cum:
        h = abs(v) / top * 46
        pos = f"bottom:50%;height:{h:.1f}%" if v >= 0 else f"top:50%;height:{h:.1f}%"
        cols.append(f'<div class="lcol"><div class="lbar {"plus" if v >= 0 else "minus"}" style="{pos}"></div><div class="lday">{_e(d.split("/")[1])}</div></div>')
    total = cum[-1][1] if cum else 0
    cls = "minus" if total < 0 else "teal"
    sign = "−" if total < 0 else "+"
    return (
        f'<style>{_PICK_CSS}</style><section class="asset"><small>今月の答え合わせ帳</small>'
        f'<h2 style="margin-top:20px">仮想購入の差引、今月の累計は <strong class="{cls}">{sign}{abs(total):,}円</strong></h2>'
        f'<div class="ledger">{"".join(cols)}</div><div class="foot" style="margin-top:60px">{_e(foot)}</div></section>'
    )
