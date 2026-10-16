"""HTTP client for the Boatrace Open API with retry logic."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx

from boatrace_ai import config
from boatrace_ai.data.models import ProgramsResponse, RaceProgram, ResultsResponse

log = logging.getLogger(__name__)


def _date_url(base: str, d: date) -> str:
    return f"{base}/{d.year}/{d.strftime('%Y%m%d')}.json"


async def _fetch_with_retry(url: str) -> dict:
    """Fetch JSON from URL with exponential backoff retry."""
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        for attempt in range(1, config.HTTP_MAX_RETRIES + 1):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < config.HTTP_MAX_RETRIES:
                    wait = 2 ** (attempt - 1)
                    log.warning("HTTP %s (attempt %d/%d), retrying in %ds...", e, attempt, config.HTTP_MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                else:
                    log.error("HTTP %s: all %d attempts failed for %s", e, config.HTTP_MAX_RETRIES, url)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 502, 503, 504) and attempt < config.HTTP_MAX_RETRIES:
                    last_error = e
                    wait = 2 ** (attempt - 1)
                    log.warning("HTTP %d (attempt %d/%d), retrying in %ds...", e.response.status_code, attempt, config.HTTP_MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                else:
                    if attempt == config.HTTP_MAX_RETRIES:
                        log.error("HTTP %d: all %d attempts failed for %s", e.response.status_code, config.HTTP_MAX_RETRIES, url)
                    raise

    raise last_error  # type: ignore[misc]


async def fetch_programs(d: date | None = None) -> ProgramsResponse:
    """Fetch race programs for a given date (default: today)."""
    if d is None:
        url = f"{config.PROGRAMS_URL}/today.json"
    else:
        url = _date_url(config.PROGRAMS_URL, d)

    data = await _fetch_with_retry(url)
    return ProgramsResponse.model_validate(data)


async def fetch_results(d: date | None = None) -> ResultsResponse:
    """Fetch race results for a given date (default: today)."""
    if d is None:
        url = f"{config.RESULTS_URL}/today.json"
    else:
        url = _date_url(config.RESULTS_URL, d)

    data = await _fetch_with_retry(url)
    return ResultsResponse.model_validate(data)


def filter_programs(
    programs: ProgramsResponse,
    stadium_number: int | None = None,
    race_number: int | None = None,
) -> list[RaceProgram]:
    """Filter programs by stadium and/or race number."""
    result = programs.programs
    if stadium_number is not None:
        result = [r for r in result if r.race_stadium_number == stadium_number]
    if race_number is not None:
        result = [r for r in result if r.race_number == race_number]
    return result
