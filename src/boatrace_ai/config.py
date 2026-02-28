"""Configuration management via environment variables."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("boatrace_ai")

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL: str = os.environ.get("BOATRACE_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS: int = int(os.environ.get("BOATRACE_MAX_TOKENS", "2048"))

_default_db = Path.home() / ".boatrace-ai" / "boatrace.db"
DB_PATH: Path = Path(os.environ.get("BOATRACE_DB_PATH", str(_default_db)))

API_BASE = "https://boatraceopenapi.github.io"
PROGRAMS_URL = f"{API_BASE}/programs/v2"
RESULTS_URL = f"{API_BASE}/results/v2"

# HTTP client settings
HTTP_TIMEOUT: int = int(os.environ.get("BOATRACE_HTTP_TIMEOUT", "30"))
HTTP_MAX_RETRIES: int = int(os.environ.get("BOATRACE_HTTP_MAX_RETRIES", "3"))


def validate() -> None:
    """Validate critical configuration. Raises ValueError if invalid."""
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY が設定されていません。\n"
            ".env ファイルに ANTHROPIC_API_KEY=sk-ant-xxx を設定してください。"
        )
    if MAX_TOKENS < 256 or MAX_TOKENS > 8192:
        raise ValueError(f"BOATRACE_MAX_TOKENS は 256〜8192 の範囲で指定してください (現在: {MAX_TOKENS})")
    if HTTP_TIMEOUT < 5 or HTTP_TIMEOUT > 120:
        raise ValueError(f"BOATRACE_HTTP_TIMEOUT は 5〜120 の範囲で指定してください (現在: {HTTP_TIMEOUT})")
    if HTTP_MAX_RETRIES < 1 or HTTP_MAX_RETRIES > 10:
        raise ValueError(f"BOATRACE_HTTP_MAX_RETRIES は 1〜10 の範囲で指定してください (現在: {HTTP_MAX_RETRIES})")
