"""Tests for configuration validation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from boatrace_ai import config


def test_validate_missing_api_key() -> None:
    with patch.object(config, "ANTHROPIC_API_KEY", ""):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            config.validate()


def test_validate_valid_api_key() -> None:
    with patch.object(config, "ANTHROPIC_API_KEY", "sk-ant-test123"):
        config.validate()  # should not raise


def test_validate_max_tokens_too_low() -> None:
    with patch.object(config, "ANTHROPIC_API_KEY", "sk-ant-test"):
        with patch.object(config, "MAX_TOKENS", 100):
            with pytest.raises(ValueError, match="MAX_TOKENS"):
                config.validate()


def test_validate_max_tokens_too_high() -> None:
    with patch.object(config, "ANTHROPIC_API_KEY", "sk-ant-test"):
        with patch.object(config, "MAX_TOKENS", 99999):
            with pytest.raises(ValueError, match="MAX_TOKENS"):
                config.validate()


def test_validate_http_timeout_too_low() -> None:
    with patch.object(config, "ANTHROPIC_API_KEY", "sk-ant-test"):
        with patch.object(config, "HTTP_TIMEOUT", 1):
            with pytest.raises(ValueError, match="HTTP_TIMEOUT"):
                config.validate()


def test_validate_http_retries_too_high() -> None:
    with patch.object(config, "ANTHROPIC_API_KEY", "sk-ant-test"):
        with patch.object(config, "HTTP_MAX_RETRIES", 50):
            with pytest.raises(ValueError, match="HTTP_MAX_RETRIES"):
                config.validate()
