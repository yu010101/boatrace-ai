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

# ML model settings
_default_model = Path.home() / ".boatrace-ai" / "model.lgb"
MODEL_PATH: Path = Path(os.environ.get("BOATRACE_MODEL_PATH", str(_default_model)))
MODEL_META_PATH: Path = MODEL_PATH.with_suffix(".meta.json")
PREDICTION_MODE: str = os.environ.get("BOATRACE_PREDICTION_MODE", "auto")  # auto|ml|claude|hybrid

# EV-based betting strategy settings
EV_MIN: float = float(os.environ.get("BOATRACE_EV_MIN", "0.20"))  # Minimum EV threshold (20%)
EV_KELLY_FRACTION: float = float(os.environ.get("BOATRACE_KELLY_FRACTION", "0.25"))  # Quarter-Kelly
EV_BANKROLL: int = int(os.environ.get("BOATRACE_BANKROLL", "100000"))  # ¥100,000

API_BASE = "https://boatraceopenapi.github.io"
PROGRAMS_URL = f"{API_BASE}/programs/v2"
RESULTS_URL = f"{API_BASE}/results/v2"

# HTTP client settings
HTTP_TIMEOUT: int = int(os.environ.get("BOATRACE_HTTP_TIMEOUT", "30"))
HTTP_MAX_RETRIES: int = int(os.environ.get("BOATRACE_HTTP_MAX_RETRIES", "3"))

# note.com settings
NOTE_EMAIL: str = os.environ.get("NOTE_EMAIL", "")
NOTE_PASSWORD: str = os.environ.get("NOTE_PASSWORD", "")
NOTE_USER_ID: str = os.environ.get("NOTE_USER_ID", "")
NOTE_ARTICLE_PRICE: int = int(os.environ.get("NOTE_ARTICLE_PRICE", "300"))

_default_session = Path.home() / ".boatrace-ai" / "note_session.json"
NOTE_SESSION_PATH: Path = Path(os.environ.get("NOTE_SESSION_PATH", str(_default_session)))

# Interval between note.com posts (seconds) to avoid rate limiting
NOTE_PUBLISH_INTERVAL: int = int(os.environ.get("NOTE_PUBLISH_INTERVAL", "10"))

# X (Twitter) API settings
TWITTER_API_KEY: str = os.environ.get("TWITTER_API_KEY", "")
TWITTER_API_SECRET: str = os.environ.get("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN: str = os.environ.get("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET: str = os.environ.get("TWITTER_ACCESS_SECRET", "")


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


def validate_note() -> None:
    """Validate note.com configuration. Raises ValueError if invalid."""
    if not NOTE_EMAIL:
        raise ValueError(
            "NOTE_EMAIL が設定されていません。\n"
            ".env ファイルに NOTE_EMAIL=your@email.com を設定してください。"
        )
    if not NOTE_PASSWORD:
        raise ValueError(
            "NOTE_PASSWORD が設定されていません。\n"
            ".env ファイルに NOTE_PASSWORD=xxx を設定してください。"
        )
    if NOTE_ARTICLE_PRICE < 100 or NOTE_ARTICLE_PRICE > 50000:
        raise ValueError(f"NOTE_ARTICLE_PRICE は 100〜50000 の範囲で指定してください (現在: {NOTE_ARTICLE_PRICE})")


def validate_twitter() -> None:
    """Validate X (Twitter) API configuration. Raises ValueError if invalid."""
    if not TWITTER_API_KEY:
        raise ValueError(
            "TWITTER_API_KEY が設定されていません。\n"
            ".env ファイルに TWITTER_API_KEY=xxx を設定してください。"
        )
    if not TWITTER_API_SECRET:
        raise ValueError(
            "TWITTER_API_SECRET が設定されていません。\n"
            ".env ファイルに TWITTER_API_SECRET=xxx を設定してください。"
        )
    if not TWITTER_ACCESS_TOKEN:
        raise ValueError(
            "TWITTER_ACCESS_TOKEN が設定されていません。\n"
            ".env ファイルに TWITTER_ACCESS_TOKEN=xxx を設定してください。"
        )
    if not TWITTER_ACCESS_SECRET:
        raise ValueError(
            "TWITTER_ACCESS_SECRET が設定されていません。\n"
            ".env ファイルに TWITTER_ACCESS_SECRET=xxx を設定してください。"
        )
