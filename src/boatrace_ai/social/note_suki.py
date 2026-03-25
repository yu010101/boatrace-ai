"""note.com auto-suki (like): search articles and give likes to target readers.

Uses httpx API calls with the same session/cookie mechanism as NoteClient.
"""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

from boatrace_ai import config
from boatrace_ai.publish.note_client import API_HEADERS, NOTE_BASE_URL, NoteClient
from boatrace_ai.storage.database import (
    get_today_suki_count,
    is_already_liked,
    save_suki_log,
)

log = logging.getLogger(__name__)

SEARCH_KEYWORDS = ["競艇予想", "ボートレース", "舟券", "ボートレース予想", "競艇"]


async def search_articles(
    cookies: dict[str, str],
    keyword: str,
    max_per_keyword: int = 20,
) -> list[dict]:
    """Search note.com for articles matching a keyword.

    Returns list of {note_key, title, creator_urlname, keyword}.
    """
    articles: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            resp = await client.get(
                f"{NOTE_BASE_URL}/api/v3/searches",
                params={"q": keyword, "context": "note", "size": max_per_keyword},
                cookies=cookies,
                headers=API_HEADERS,
            )
            if resp.status_code != 200:
                log.warning(
                    "Search API returned %d for keyword '%s'", resp.status_code, keyword
                )
                return articles

            data = resp.json()
            notes = data.get("data", {}).get("notes", {}).get("items", [])

            for note in notes:
                note_key = note.get("key", "")
                title = note.get("name", "")
                creator = note.get("user", {}).get("urlname", "")

                if not note_key:
                    continue
                # Skip own articles
                if creator == config.NOTE_URLNAME:
                    continue
                # Skip already liked
                if is_already_liked(note_key):
                    continue

                articles.append({
                    "note_key": note_key,
                    "title": title,
                    "creator": creator,
                    "keyword": keyword,
                })

            log.info("Keyword '%s': found %d new articles", keyword, len(articles))

    except Exception as e:
        log.warning("Failed to search keyword '%s': %s", keyword, e)

    return articles


async def like_article(cookies: dict[str, str], note_key: str) -> bool:
    """Give suki (like) to a note.com article.

    Returns True if the like was successful.
    """
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            resp = await client.put(
                f"{NOTE_BASE_URL}/api/v3/notes/{note_key}/like",
                cookies=cookies,
                headers=API_HEADERS,
            )
            if resp.status_code in (200, 204):
                log.info("Liked note %s", note_key)
                return True
            else:
                log.warning(
                    "Like API returned %d for note %s: %s",
                    resp.status_code, note_key, resp.text[:200],
                )
                return False
    except Exception as e:
        log.warning("Failed to like note %s: %s", note_key, e)
        return False


async def execute_note_suki(
    max_likes: int | None = None,
    keywords: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute note.com auto-suki workflow.

    Returns dict with suki results summary.
    """
    if max_likes is None:
        max_likes = config.NOTE_SUKI_MAX_PER_DAY

    # Check daily limit
    today_count = get_today_suki_count()
    remaining = max(0, max_likes - today_count)
    if remaining == 0:
        log.info("Daily suki limit reached (%d/%d)", today_count, max_likes)
        return {
            "discovered": 0,
            "liked": 0,
            "skipped": 0,
            "already_at_limit": True,
        }

    # Authenticate using NoteClient's session mechanism
    client = NoteClient()
    await client.ensure_logged_in()
    cookies = client._cookies

    # Search for articles
    all_keywords = keywords or SEARCH_KEYWORDS
    # Randomly pick a subset of keywords to scan
    scan_count = min(3, len(all_keywords))
    selected_keywords = random.sample(all_keywords, scan_count)
    log.info("Scanning %d/%d keywords: %s", scan_count, len(all_keywords), selected_keywords)

    all_articles: list[dict] = []
    seen_keys: set[str] = set()

    for kw in selected_keywords:
        articles = await search_articles(cookies, kw)
        for article in articles:
            if article["note_key"] not in seen_keys:
                seen_keys.add(article["note_key"])
                all_articles.append(article)

    log.info("Discovered %d new articles to like", len(all_articles))

    if dry_run:
        return {
            "discovered": len(all_articles),
            "liked": 0,
            "skipped": 0,
            "dry_run": True,
            "articles": all_articles,
        }

    # Shuffle for natural-looking behavior
    random.shuffle(all_articles)

    liked = 0
    skipped = 0

    for article in all_articles:
        if liked >= remaining:
            log.info("Reached daily limit (%d likes)", liked)
            break

        note_key = article["note_key"]
        success = await like_article(cookies, note_key)

        if success:
            save_suki_log(
                note_key=note_key,
                title=article.get("title", ""),
                creator=article.get("creator", ""),
                keyword=article.get("keyword", ""),
            )
            liked += 1
            log.info(
                "Suki %d/%d: %s by @%s (keyword: %s)",
                liked, remaining,
                article.get("title", "")[:30],
                article.get("creator", ""),
                article.get("keyword", ""),
            )

            # Random delay between likes
            if liked < remaining and liked < len(all_articles):
                delay = random.uniform(
                    config.NOTE_SUKI_DELAY_MIN, config.NOTE_SUKI_DELAY_MAX
                )
                log.info("Waiting %.0f seconds...", delay)
                await asyncio.sleep(delay)
        else:
            skipped += 1

    return {
        "discovered": len(all_articles),
        "liked": liked,
        "skipped": skipped,
    }
