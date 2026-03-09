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

    # Truncate long titles and add line breaks
    display_title = title
    if len(display_title) > 40:
        display_title = display_title[:40] + "..."

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {WIDTH}px;
    height: {HEIGHT}px;
    background: linear-gradient(135deg, {COLOR_MAIN} 0%, {COLOR_BG} 100%);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                 "Noto Sans JP", "Yu Gothic", sans-serif;
    overflow: hidden;
    position: relative;
  }}
  /* Decorative accent line at top */
  .accent-top {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 6px;
    background: linear-gradient(90deg, {COLOR_ACCENT}, transparent);
  }}
  /* Decorative accent line at bottom */
  .accent-bottom {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 6px;
    background: linear-gradient(90deg, transparent, {COLOR_ACCENT});
  }}
  .icon {{
    font-size: 80px;
    color: {icon_color};
    margin-bottom: 20px;
    text-shadow: 0 0 30px {icon_color}40;
  }}
  .title {{
    font-size: 42px;
    font-weight: 900;
    color: {COLOR_TEXT};
    text-align: center;
    padding: 0 80px;
    line-height: 1.4;
    max-width: 1100px;
    word-break: break-all;
  }}
  .brand {{
    position: absolute;
    bottom: 40px;
    right: 60px;
    font-size: 32px;
    font-weight: 700;
    color: {COLOR_ACCENT};
    letter-spacing: 4px;
  }}
  .brand-sub {{
    position: absolute;
    bottom: 80px;
    right: 60px;
    font-size: 16px;
    color: {COLOR_TEXT}80;
    letter-spacing: 2px;
  }}
  /* Subtle grid pattern */
  .grid-overlay {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image:
      linear-gradient({COLOR_ACCENT}08 1px, transparent 1px),
      linear-gradient(90deg, {COLOR_ACCENT}08 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
  }}
</style>
</head>
<body>
  <div class="accent-top"></div>
  <div class="accent-bottom"></div>
  <div class="grid-overlay"></div>
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
