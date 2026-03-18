"""note.com auto-follow: discover and follow creators in boatrace-related tags.

Reuses NoteClient's Playwright browser and authentication pattern.
"""

from __future__ import annotations

import asyncio
import logging
import random

from boatrace_ai import config
from boatrace_ai.publish.note_client import NoteClient
from boatrace_ai.storage.database import (
    get_today_follow_count,
    is_already_followed,
    save_follow_log,
)

log = logging.getLogger(__name__)

TARGET_TAGS = ["競艇予想", "ボートレース予想", "ボートレース", "競艇", "舟券"]


async def discover_creators(
    page,
    tags: list[str] | None = None,
    max_per_tag: int = 10,
) -> list[dict]:
    """Discover creators from note.com hashtag pages.

    Returns list of {urlname, display_name, source_tag}, deduplicated and
    filtered against already-followed users.
    """
    all_tags = tags or TARGET_TAGS
    # Randomly pick a subset of tags to scan (avoid scanning all every time)
    scan_count = min(config.NOTE_FOLLOW_MAX_TAGS, len(all_tags))
    tags = random.sample(all_tags, scan_count)
    log.info("Scanning %d/%d tags: %s", scan_count, len(all_tags), tags)
    seen: set[str] = set()
    creators: list[dict] = []

    for tag in tags:
        url = f"https://note.com/hashtag/{tag}"
        log.info("Scanning tag: %s", tag)

        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Scroll down to load more articles
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(1)

            # Extract creator links from article cards
            # note.com article links follow pattern: /username/n/xxxxx
            links = await page.query_selector_all('a[href*="/n/"]')
            tag_count = 0

            for link in links:
                if tag_count >= max_per_tag:
                    break

                href = await link.get_attribute("href") or ""
                # Extract urlname from /username/n/xxxxx pattern
                parts = href.strip("/").split("/")
                if len(parts) >= 3 and parts[-2] == "n":
                    urlname = parts[-3] if len(parts) > 3 else parts[0]
                else:
                    continue

                if not urlname or urlname in seen:
                    continue
                if urlname in ("hashtag", "api", "login", "signup"):
                    continue

                if is_already_followed(urlname):
                    continue

                seen.add(urlname)
                tag_count += 1

                # Try to get display name from the page
                display_name = urlname
                try:
                    name_el = await page.query_selector(
                        f'a[href="/{urlname}"] span, a[href="/{urlname}"]'
                    )
                    if name_el:
                        display_name = (await name_el.text_content() or urlname).strip()
                except Exception:
                    pass

                creators.append({
                    "urlname": urlname,
                    "display_name": display_name,
                    "source_tag": tag,
                })

            log.info("Tag '%s': found %d new creators", tag, tag_count)

        except Exception as e:
            log.warning("Failed to scan tag '%s': %s", tag, e)
            continue

    return creators


async def follow_user(page, urlname: str) -> bool:
    """Follow a user on note.com by visiting their profile.

    Returns True if follow was successful.
    """
    url = f"https://note.com/{urlname}"
    log.info("Visiting profile: %s", url)

    try:
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Look for the follow button (not "フォロー中")
        follow_btn = page.locator('button:has-text("フォロー")')
        count = await follow_btn.count()

        for i in range(count):
            btn = follow_btn.nth(i)
            text = (await btn.text_content() or "").strip()
            # Skip if already following
            if "フォロー中" in text:
                log.info("Already following %s", urlname)
                return False
            if text == "フォロー" or text == "フォローする":
                await btn.click()
                await asyncio.sleep(2)
                log.info("Followed %s", urlname)
                return True

        log.warning("Follow button not found for %s", urlname)
        return False

    except Exception as e:
        log.warning("Failed to follow %s: %s", urlname, e)
        return False


async def execute_note_follow(
    max_follows: int | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute note.com auto-follow workflow.

    Returns dict with follow results summary.
    """
    if max_follows is None:
        max_follows = config.NOTE_FOLLOW_MAX_PER_DAY
    # Check daily limit
    today_count = get_today_follow_count()
    remaining = max(0, max_follows - today_count)
    if remaining == 0:
        log.info("Daily follow limit reached (%d/%d)", today_count, max_follows)
        return {
            "discovered": 0,
            "followed": 0,
            "skipped": 0,
            "already_at_limit": True,
        }

    client = NoteClient()
    await client.ensure_logged_in()
    await client.open_browser()

    try:
        page = await client._browser_context.new_page()

        # Discover creators
        creators = await discover_creators(page, tags=tags)
        log.info("Discovered %d new creators", len(creators))

        if dry_run:
            await page.close()
            return {
                "discovered": len(creators),
                "followed": 0,
                "skipped": 0,
                "dry_run": True,
                "creators": creators,
            }

        # Shuffle for natural-looking behavior
        random.shuffle(creators)

        followed = 0
        skipped = 0

        for creator in creators:
            if followed >= remaining:
                log.info("Reached daily limit (%d follows)", followed)
                break

            urlname = creator["urlname"]
            success = await follow_user(page, urlname)

            if success:
                save_follow_log(
                    target_urlname=urlname,
                    target_display_name=creator.get("display_name"),
                    source_tag=creator.get("source_tag"),
                )
                followed += 1
                log.info(
                    "Follow %d/%d: %s (tag: %s)",
                    followed, remaining, urlname, creator.get("source_tag"),
                )

                # Random delay between follows
                if followed < remaining and followed < len(creators):
                    delay = random.uniform(config.NOTE_FOLLOW_DELAY_MIN, config.NOTE_FOLLOW_DELAY_MAX)
                    log.info("Waiting %.0f seconds...", delay)
                    await asyncio.sleep(delay)
            else:
                skipped += 1

        await page.close()

        return {
            "discovered": len(creators),
            "followed": followed,
            "skipped": skipped,
        }

    finally:
        await client.close_browser()
