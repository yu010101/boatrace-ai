"""Tests for the API client using respx for HTTP mocking."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from boatrace_ai.data.client import fetch_programs, fetch_results, filter_programs
from boatrace_ai.data.models import ProgramsResponse


@pytest.mark.asyncio
async def test_fetch_programs_today(programs_json: dict) -> None:
    with respx.mock:
        respx.get("https://boatraceopenapi.github.io/programs/v2/today.json").mock(
            return_value=httpx.Response(200, json=programs_json)
        )
        result = await fetch_programs()
        assert len(result.programs) > 0


@pytest.mark.asyncio
async def test_fetch_programs_by_date(programs_json: dict) -> None:
    d = date(2026, 2, 28)
    with respx.mock:
        respx.get("https://boatraceopenapi.github.io/programs/v2/2026/20260228.json").mock(
            return_value=httpx.Response(200, json=programs_json)
        )
        result = await fetch_programs(d)
        assert len(result.programs) > 0


@pytest.mark.asyncio
async def test_fetch_results(results_json: dict) -> None:
    d = date(2026, 2, 27)
    with respx.mock:
        respx.get("https://boatraceopenapi.github.io/results/v2/2026/20260227.json").mock(
            return_value=httpx.Response(200, json=results_json)
        )
        result = await fetch_results(d)
        assert len(result.results) > 0


@pytest.mark.asyncio
async def test_fetch_programs_http_error() -> None:
    with respx.mock:
        respx.get("https://boatraceopenapi.github.io/programs/v2/today.json").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_programs()


@pytest.mark.asyncio
async def test_fetch_retry_on_503(programs_json: dict) -> None:
    """Should retry on 503 and succeed on second attempt."""
    with respx.mock:
        route = respx.get("https://boatraceopenapi.github.io/programs/v2/today.json")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=programs_json),
        ]
        result = await fetch_programs()
        assert len(result.programs) > 0
        assert route.call_count == 2


def test_filter_programs(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    # Filter by stadium
    stadium_num = resp.programs[0].race_stadium_number
    filtered = filter_programs(resp, stadium_number=stadium_num)
    assert all(r.race_stadium_number == stadium_num for r in filtered)

    # Filter by race number
    race_num = resp.programs[0].race_number
    filtered = filter_programs(resp, race_number=race_num)
    assert all(r.race_number == race_num for r in filtered)


def test_filter_programs_no_match(programs_json: dict) -> None:
    resp = ProgramsResponse.model_validate(programs_json)
    filtered = filter_programs(resp, stadium_number=99)
    assert filtered == []
