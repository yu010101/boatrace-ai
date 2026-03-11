"""Generate OGP eyecatch images for note.com articles using Playwright.

Renders an HTML template to a 1280x670px PNG screenshot with brand styling.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Brand colors
COLOR_MAIN = "#0A1628"
COLOR_ACCENT = "#00D4FF"
COLOR_TEXT = "#E8EAED"
COLOR_BG = "#0D1B2A"
COLOR_HIT = "#00E676"

# Article type to icon mapping
ARTICLE_ICONS: dict[str, tuple[str, str]] = {
    "prediction": ("\u25ce", COLOR_ACCENT),   # ◎
    "grades": ("\u25ce", COLOR_ACCENT),        # ◎
    "results": ("\u7684\u4e2d", COLOR_HIT),    # 的中
    "midday": ("\u7684\u4e2d", COLOR_HIT),     # 的中
    "track_record": ("\u63a8\u79fb", COLOR_ACCENT),  # 推移
    "membership": ("\u2606", COLOR_ACCENT),    # ☆
}

# OGP image dimensions (note.com recommended)
WIDTH = 1280
HEIGHT = 670


def _build_eyecatch_html(
    title: str,
    article_type: str = "prediction",
    subtitle: str | None = None,
) -> str:
    """Build HTML template for the eyecatch image."""
    icon_text, icon_color = ARTICLE_ICONS.get(
        article_type, ("\u25ce", COLOR_ACCENT)
    )

    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            f'<div style="font-size: 24px; color: {COLOR_ACCENT}; '
            f'margin-top: 12px; letter-spacing: 2px;">{subtitle}</div>'
        )

    # Smart title truncation — split at natural break points
    display_title = title
    # Remove trailing " — 水理AI" for cleaner display
    if " — 水理AI" in display_title:
        display_title = display_title.replace(" — 水理AI", "")
    if len(display_title) > 45:
        display_title = display_title[:45] + "..."

    # Article type label for badge
    type_labels = {
        "prediction": "AI\u4e88\u6e2c",   # AI予測
        "grades": "\u5168\u30ec\u30fc\u30b9\u4e88\u6e2c",  # 全レース予測
        "results": "\u7d50\u679c\u30ec\u30dd\u30fc\u30c8",  # 結果レポート
        "midday": "\u5348\u524d\u901f\u5831",  # 午前速報
        "track_record": "\u5b9f\u7e3e\u63a8\u79fb",  # 実績推移
        "membership": "\u30e1\u30f3\u30d0\u30fc\u30b7\u30c3\u30d7",  # メンバーシップ
    }
    badge_text = type_labels.get(article_type, "AI\u4e88\u6e2c")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {WIDTH}px;
    height: {HEIGHT}px;
    background: linear-gradient(160deg, {COLOR_MAIN} 0%, #0F2035 40%, {COLOR_BG} 100%);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                 "Noto Sans JP", "Yu Gothic", sans-serif;
    overflow: hidden;
    position: relative;
  }}
  /* Accent bar at top */
  .accent-top {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 5px;
    background: linear-gradient(90deg, {COLOR_ACCENT}, {COLOR_ACCENT}60, transparent);
  }}
  /* Wave decoration at bottom */
  .wave {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 120px;
    opacity: 0.08;
  }}
  .wave svg {{
    width: 100%;
    height: 100%;
  }}
  /* Glow circle behind icon */
  .glow {{
    position: absolute;
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: radial-gradient(circle, {icon_color}18, transparent 70%);
    top: 50%;
    left: 50%;
    transform: translate(-50%, -65%);
    pointer-events: none;
  }}
  /* Badge */
  .badge {{
    display: inline-block;
    padding: 6px 24px;
    border: 1.5px solid {icon_color}90;
    border-radius: 4px;
    font-size: 18px;
    font-weight: 700;
    color: {icon_color};
    letter-spacing: 3px;
    margin-bottom: 24px;
    text-transform: uppercase;
  }}
  .icon {{
    font-size: 72px;
    color: {icon_color};
    margin-bottom: 16px;
    text-shadow: 0 0 40px {icon_color}30;
    position: relative;
    z-index: 1;
  }}
  .title {{
    font-size: 40px;
    font-weight: 900;
    color: {COLOR_TEXT};
    text-align: center;
    padding: 0 100px;
    line-height: 1.45;
    max-width: 1100px;
    word-break: break-all;
    position: relative;
    z-index: 1;
  }}
  .brand {{
    position: absolute;
    bottom: 30px;
    right: 50px;
    font-size: 36px;
    font-weight: 900;
    color: {COLOR_ACCENT};
    letter-spacing: 5px;
  }}
  .brand-sub {{
    position: absolute;
    bottom: 72px;
    right: 50px;
    font-size: 14px;
    color: {COLOR_TEXT}60;
    letter-spacing: 3px;
    text-transform: uppercase;
  }}
  /* Vertical accent line left */
  .side-line {{
    position: absolute;
    left: 40px;
    top: 60px;
    bottom: 60px;
    width: 3px;
    background: linear-gradient(180deg, {COLOR_ACCENT}40, transparent);
    border-radius: 2px;
  }}
  /* Subtle data grid */
  .grid-overlay {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image:
      linear-gradient({COLOR_ACCENT}06 1px, transparent 1px),
      linear-gradient(90deg, {COLOR_ACCENT}06 1px, transparent 1px);
    background-size: 50px 50px;
    pointer-events: none;
  }}
</style>
</head>
<body>
  <div class="accent-top"></div>
  <div class="grid-overlay"></div>
  <div class="side-line"></div>
  <div class="glow"></div>
  <div class="wave">
    <svg viewBox="0 0 1280 120" preserveAspectRatio="none">
      <path d="M0,60 C320,120 640,0 960,60 C1120,90 1200,30 1280,60 L1280,120 L0,120 Z"
            fill="{COLOR_ACCENT}" />
    </svg>
  </div>
  <div class="badge">{badge_text}</div>
  <div class="icon">{icon_text}</div>
  <div class="title">{display_title}</div>
  {subtitle_html}
  <div class="brand-sub">BOATRACE AI PREDICTION</div>
  <div class="brand">\u6c34\u7406AI</div>
</body>
</html>"""


async def generate_eyecatch(
    title: str,
    article_type: str = "prediction",
    subtitle: str | None = None,
) -> Path | None:
    """Generate an OGP eyecatch image using Playwright.

    Args:
        title: Article title to display on the image.
        article_type: One of prediction, grades, results, midday,
                      track_record, membership.
        subtitle: Optional subtitle line (e.g. "Sランク 5レース").

    Returns:
        Path to the generated PNG file (in a temp directory), or None on failure.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("playwright が未インストールのためアイキャッチ生成をスキップ")
        return None

    html_content = _build_eyecatch_html(title, article_type, subtitle)

    # Write HTML to temp file
    tmp_dir = tempfile.mkdtemp(prefix="eyecatch_")
    html_path = Path(tmp_dir) / "eyecatch.html"
    png_path = Path(tmp_dir) / "eyecatch.png"
    html_path.write_text(html_content, encoding="utf-8")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                page = await browser.new_page(
                    viewport={"width": WIDTH, "height": HEIGHT},
                )
                await page.goto(f"file://{html_path}")
                await page.screenshot(path=str(png_path), type="png")
                log.info("Eyecatch generated: %s", png_path)
                return png_path
            finally:
                await browser.close()
    except Exception as e:
        log.error("アイキャッチ画像の生成に失敗: %s", e)
        return None


# ── Stats chart generation ────────────────────────────────────

CHART_WIDTH = 800
CHART_HEIGHT = 400


def _build_chart_html(
    accuracy_trend: list[dict],
    roi_trend: list[dict],
) -> str:
    """Build HTML for a 30-day stats chart (CSS-only bars + SVG line)."""
    # Use last 14 days for readability
    acc_data = list(reversed(accuracy_trend[:14]))
    roi_map = {r["date"]: r for r in roi_trend}

    # Build bar data
    bars_html = []
    svg_points = []
    max_roi = 200  # cap at 200%

    for i, acc in enumerate(acc_data):
        d = acc["date"]
        date_label = d[5:]  # "MM-DD"
        hit_pct = round(acc["hit_1st_rate"] * 100)
        roi_day = roi_map.get(d)
        roi_pct = round(roi_day["roi"] * 100) if roi_day else 0
        roi_display = min(roi_pct, max_roi)

        # Bar height (ROI, 0-200% mapped to 0-160px)
        bar_h = max(2, round(roi_display / max_roi * 160))
        bar_color = COLOR_HIT if roi_pct >= 100 else COLOR_ACCENT

        # SVG point for hit rate line (0-100% mapped to 180-20)
        svg_y = 180 - round(hit_pct / 100 * 160)
        svg_x = 30 + i * 52
        svg_points.append(f"{svg_x},{svg_y}")

        bars_html.append(
            f'<div class="bar-col" style="left:{i * 52}px">'
            f'<div class="bar" style="height:{bar_h}px;background:{bar_color}"></div>'
            f'<div class="bar-label">{date_label}</div>'
            f'</div>'
        )

    polyline = " ".join(svg_points)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:{CHART_WIDTH}px; height:{CHART_HEIGHT}px;
  background:{COLOR_MAIN}; font-family:"Hiragino Sans",sans-serif;
  position:relative; overflow:hidden;
}}
.title {{ color:{COLOR_TEXT}; font-size:20px; font-weight:700; padding:16px 24px 8px; }}
.legend {{ display:flex; gap:24px; padding:0 24px 8px; font-size:13px; color:{COLOR_TEXT}90; }}
.legend-item {{ display:flex; align-items:center; gap:6px; }}
.legend-box {{ width:16px; height:10px; border-radius:2px; }}
.chart {{ position:relative; height:220px; margin:0 24px; }}
.bar-col {{ position:absolute; bottom:24px; width:44px; text-align:center; }}
.bar {{ width:32px; margin:0 auto; border-radius:3px 3px 0 0; min-height:2px; }}
.bar-label {{ font-size:10px; color:{COLOR_TEXT}60; margin-top:4px; }}
.line-svg {{ position:absolute; top:0; left:0; width:100%; height:200px; }}
.brand {{ position:absolute; bottom:8px; right:16px; font-size:14px; color:{COLOR_ACCENT}80; font-weight:700; }}
</style></head><body>
<div class="title">直近14日間の的中率・ROI推移</div>
<div class="legend">
  <div class="legend-item"><div class="legend-box" style="background:{COLOR_ACCENT}"></div>ROI(%)</div>
  <div class="legend-item"><div class="legend-box" style="background:{COLOR_HIT}"></div>ROI 100%+</div>
  <div class="legend-item"><div class="legend-box" style="background:transparent;border:2px solid #FF6B6B"></div>1着的中率(%)</div>
</div>
<div class="chart">
  {''.join(bars_html)}
  <svg class="line-svg" viewBox="0 0 {CHART_WIDTH} 200" preserveAspectRatio="none">
    <polyline points="{polyline}" fill="none" stroke="#FF6B6B" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round"/>
    {"".join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="4" fill="#FF6B6B"/>' for p in svg_points)}
  </svg>
</div>
<div class="brand">水理AI</div>
</body></html>"""


async def generate_stats_chart(
    accuracy_trend: list[dict],
    roi_trend: list[dict],
) -> Path | None:
    """Generate a 30-day stats chart image (HTML→PNG via Playwright).

    Args:
        accuracy_trend: From get_accuracy_trend(30)
        roi_trend: From get_roi_trend(30)

    Returns:
        Path to PNG, or None on failure.
    """
    if not accuracy_trend:
        return None

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("playwright が未インストールのためグラフ生成をスキップ")
        return None

    html_content = _build_chart_html(accuracy_trend, roi_trend)

    tmp_dir = tempfile.mkdtemp(prefix="chart_")
    html_path = Path(tmp_dir) / "chart.html"
    png_path = Path(tmp_dir) / "chart.png"
    html_path.write_text(html_content, encoding="utf-8")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                page = await browser.new_page(
                    viewport={"width": CHART_WIDTH, "height": CHART_HEIGHT},
                )
                await page.goto(f"file://{html_path}")
                await page.screenshot(path=str(png_path), type="png")
                log.info("Stats chart generated: %s", png_path)
                return png_path
            finally:
                await browser.close()
    except Exception as e:
        log.error("グラフ画像の生成に失敗: %s", e)
        return None
