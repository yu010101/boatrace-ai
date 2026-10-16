"""Tests for eyecatch image generation (Gemini + HTML/Playwright fallback)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from boatrace_ai import config
from boatrace_ai.publish.eyecatch import (
    _generate_html_eyecatch,
    generate_eyecatch,
    generate_gemini_eyecatch,
)


# ── Gemini eyecatch tests ────────────────────────────────────


async def test_gemini_eyecatch_success(tmp_path: Path) -> None:
    """API mock succeeds → returns a PNG path."""
    fake_image = MagicMock()
    fake_image.image.image_bytes = b"\x89PNG fake image bytes"

    fake_response = MagicMock()
    fake_response.generated_images = [fake_image]

    mock_client = MagicMock()
    mock_client.models.generate_images.return_value = fake_response

    with (
        patch.object(config, "GOOGLE_API_KEY", "test-key"),
        patch.object(config, "GEMINI_EYECATCH_ENABLED", True),
        patch.object(config, "GEMINI_IMAGE_MODEL", "imagen-4.0-generate-001"),
        patch("google.genai.Client", return_value=mock_client),
        patch("google.genai.types") as mock_types,
    ):
        result = await generate_gemini_eyecatch("テスト記事タイトル", "prediction")

    assert result is not None
    assert result.name == "eyecatch.png"
    assert result.read_bytes() == b"\x89PNG fake image bytes"


async def test_gemini_eyecatch_no_api_key() -> None:
    """No GOOGLE_API_KEY → returns None immediately."""
    with (
        patch.object(config, "GOOGLE_API_KEY", ""),
        patch.object(config, "GEMINI_EYECATCH_ENABLED", True),
    ):
        result = await generate_gemini_eyecatch("タイトル")

    assert result is None


async def test_gemini_eyecatch_disabled() -> None:
    """GEMINI_EYECATCH_ENABLED=false → returns None."""
    with (
        patch.object(config, "GOOGLE_API_KEY", "test-key"),
        patch.object(config, "GEMINI_EYECATCH_ENABLED", False),
    ):
        result = await generate_gemini_eyecatch("タイトル")

    assert result is None


async def test_gemini_eyecatch_import_error() -> None:
    """google-genai not installed → returns None gracefully."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "google" or name.startswith("google."):
            raise ImportError("No module named 'google'")
        return real_import(name, *args, **kwargs)

    with (
        patch.object(config, "GOOGLE_API_KEY", "test-key"),
        patch.object(config, "GEMINI_EYECATCH_ENABLED", True),
        patch("builtins.__import__", side_effect=fake_import),
    ):
        result = await generate_gemini_eyecatch("タイトル")

    assert result is None


async def test_gemini_eyecatch_api_failure() -> None:
    """API raises exception → returns None (fallback)."""
    mock_client = MagicMock()
    mock_client.models.generate_images.side_effect = RuntimeError("API error")

    with (
        patch.object(config, "GOOGLE_API_KEY", "test-key"),
        patch.object(config, "GEMINI_EYECATCH_ENABLED", True),
        patch.object(config, "GEMINI_IMAGE_MODEL", "imagen-4.0-generate-001"),
        patch("google.genai.Client", return_value=mock_client),
        patch("google.genai.types") as mock_types,
    ):
        result = await generate_gemini_eyecatch("タイトル")

    assert result is None


# ── Integration tests (generate_eyecatch orchestration) ──────


async def test_generate_eyecatch_gemini_then_fallback() -> None:
    """Gemini succeeds → returns Gemini path, no HTML fallback called."""
    gemini_path = Path("/tmp/gemini/eyecatch.png")

    with (
        patch(
            "boatrace_ai.publish.eyecatch.generate_gemini_eyecatch",
            new_callable=AsyncMock,
            return_value=gemini_path,
        ) as mock_gemini,
        patch(
            "boatrace_ai.publish.eyecatch._generate_html_eyecatch",
            new_callable=AsyncMock,
        ) as mock_html,
    ):
        result = await generate_eyecatch("タイトル", "prediction")

    assert result == gemini_path
    mock_gemini.assert_awaited_once()
    mock_html.assert_not_awaited()


async def test_generate_eyecatch_fallback_to_html() -> None:
    """Gemini fails → falls back to HTML/Playwright."""
    html_path = Path("/tmp/html/eyecatch.png")

    with (
        patch(
            "boatrace_ai.publish.eyecatch.generate_gemini_eyecatch",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_gemini,
        patch(
            "boatrace_ai.publish.eyecatch._generate_html_eyecatch",
            new_callable=AsyncMock,
            return_value=html_path,
        ) as mock_html,
    ):
        result = await generate_eyecatch("タイトル", "prediction")

    assert result == html_path
    mock_gemini.assert_awaited_once()
    mock_html.assert_awaited_once()


# ── HTML/Playwright fallback tests ───────────────────────────


async def test_html_eyecatch_playwright_import_error() -> None:
    """Playwright not installed → returns None."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "playwright" or name.startswith("playwright."):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        result = await _generate_html_eyecatch("タイトル")

    assert result is None
