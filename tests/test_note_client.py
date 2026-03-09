"""Tests for NoteClient: session management, API calls (all mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from boatrace_ai.publish.note_client import (
    NOTE_API_URL,
    NoteAuthError,
    NoteClient,
    NotePublishError,
)


@pytest.fixture
def tmp_session(tmp_path: Path) -> Path:
    return tmp_path / "note_session.json"


@pytest.fixture
def client(tmp_session: Path) -> NoteClient:
    return NoteClient(session_path=tmp_session)


# ── Session persistence ───────────────────────────────────


class TestSessionPersistence:
    def test_save_and_load(self, client: NoteClient, tmp_session: Path) -> None:
        client._cookies = {"NOTE_SESSION_V5": "abc", "XSRF-TOKEN": "xyz"}
        client._xsrf_token = "xyz"
        client._save_session()

        assert tmp_session.exists()
        data = json.loads(tmp_session.read_text())
        assert data["cookies"]["NOTE_SESSION_V5"] == "abc"
        assert data["xsrf_token"] == "xyz"

        client2 = NoteClient(session_path=tmp_session)
        assert client2._load_session() is True
        assert client2._cookies["NOTE_SESSION_V5"] == "abc"
        assert client2._xsrf_token == "xyz"

    def test_load_missing_file(self, client: NoteClient) -> None:
        assert client._load_session() is False

    def test_load_corrupted_file(self, client: NoteClient, tmp_session: Path) -> None:
        tmp_session.write_text("not json")
        assert client._load_session() is False

    def test_load_missing_keys(self, client: NoteClient, tmp_session: Path) -> None:
        tmp_session.write_text(json.dumps({"cookies": {}}))
        assert client._load_session() is False

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "session.json"
        c = NoteClient(session_path=deep_path)
        c._cookies = {"x": "1"}
        c._xsrf_token = "t"
        c._save_session()
        assert deep_path.exists()


# ── Session validation ────────────────────────────────────


class TestSessionValidation:
    @pytest.mark.asyncio
    async def test_valid_session(self, client: NoteClient) -> None:
        client._cookies = {"NOTE_SESSION_V5": "abc"}
        client._xsrf_token = "xyz"

        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client_instance

            assert await client._is_session_valid() is True

    @pytest.mark.asyncio
    async def test_invalid_session_401(self, client: NoteClient) -> None:
        client._cookies = {"NOTE_SESSION_V5": "expired"}
        client._xsrf_token = "xyz"

        mock_resp = AsyncMock()
        mock_resp.status_code = 401

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client_instance

            assert await client._is_session_valid() is False

    @pytest.mark.asyncio
    async def test_empty_cookies_invalid(self, client: NoteClient) -> None:
        assert await client._is_session_valid() is False

    @pytest.mark.asyncio
    async def test_network_error_invalid(self, client: NoteClient) -> None:
        client._cookies = {"NOTE_SESSION_V5": "abc"}
        client._xsrf_token = "xyz"

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=httpx.ConnectError("fail"))
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client_instance

            assert await client._is_session_valid() is False


# ── Login ─────────────────────────────────────────────────


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_missing_playwright(self, client: NoteClient) -> None:
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            with patch("builtins.__import__", side_effect=ImportError("no playwright")):
                with pytest.raises(NoteAuthError, match="playwright"):
                    await client.login()


# ── _create_draft ─────────────────────────────────────────


class TestCreateDraft:
    @pytest.mark.asyncio
    async def test_create_draft_success(self, client: NoteClient) -> None:
        client._cookies = {"_note_session_v5": "abc"}

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "data": {"id": 12345, "key": "nabc123"}
        }

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            result = await client._create_draft()
            assert result["id"] == 12345
            assert result["key"] == "nabc123"

            # Verify API call
            call_args = mock_http.post.call_args
            assert call_args.args[0] == NOTE_API_URL
            assert call_args.kwargs["json"] == {"template_key": None}

    @pytest.mark.asyncio
    async def test_create_draft_failure(self, client: NoteClient) -> None:
        client._cookies = {"_note_session_v5": "abc"}

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server Error"

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            with pytest.raises(NotePublishError, match="下書き作成に失敗"):
                await client._create_draft()


# ── _save_draft_content ───────────────────────────────────


class TestSaveDraftContent:
    @pytest.mark.asyncio
    async def test_save_content_success(self, client: NoteClient) -> None:
        client._cookies = {"_note_session_v5": "abc"}

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"data": {"result": True}}

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            await client._save_draft_content(
                12345, "Test Title", "<p>Body</p>", ["tag1"]
            )

            call_args = mock_http.post.call_args
            assert "draft_save?id=12345" in call_args.args[0]
            payload = call_args.kwargs["json"]
            assert payload["name"] == "Test Title"
            assert payload["body"] == "<p>Body</p>"
            assert payload["hashtags"] == ["tag1"]

    @pytest.mark.asyncio
    async def test_save_content_no_hashtags(self, client: NoteClient) -> None:
        client._cookies = {"_note_session_v5": "abc"}

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"data": {"result": True}}

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            await client._save_draft_content(12345, "Title", "<p>Body</p>")

            payload = mock_http.post.call_args.kwargs["json"]
            assert "hashtags" not in payload

    @pytest.mark.asyncio
    async def test_save_content_failure(self, client: NoteClient) -> None:
        client._cookies = {"_note_session_v5": "abc"}

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"

        with patch("boatrace_ai.publish.note_client.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_http

            with pytest.raises(NotePublishError, match="下書き保存に失敗"):
                await client._save_draft_content(12345, "Title", "<p>Body</p>")


# ── create_and_publish ────────────────────────────────────


class TestCreateAndPublish:
    @pytest.mark.asyncio
    async def test_publish_success(self, client: NoteClient) -> None:
        """Full publish flow: create draft → save content → publish via editor."""
        client._cookies = {"_note_session_v5": "abc"}

        with (
            patch.object(
                client, "_create_draft",
                return_value={"id": 12345, "key": "nabc123"},
            ) as mock_create,
            patch.object(client, "_save_draft_content") as mock_save,
            patch.object(
                client, "_publish_via_editor",
                return_value={"url": "https://note.com/user/n/nabc123", "draft_key": "nabc123"},
            ) as mock_publish,
        ):
            result = await client.create_and_publish(
                title="Test Article",
                html_body="<h1>Test</h1><pay><p>Paid</p>",
                price=300,
                hashtags=["test"],
            )

            assert result["draft_key"] == "nabc123"

            mock_create.assert_called_once()
            mock_save.assert_called_once_with(
                12345, "Test Article", "<h1>Test</h1><pay><p>Paid</p>", ["test"],
                eyecatch_src=None,
            )
            mock_publish.assert_called_once_with("nabc123", 300, ["test"])

    @pytest.mark.asyncio
    async def test_publish_default_price(self, client: NoteClient) -> None:
        """Default price from config is used when not specified."""
        client._cookies = {"_note_session_v5": "abc"}

        with (
            patch.object(client, "_create_draft", return_value={"id": 1, "key": "nk1"}),
            patch.object(client, "_save_draft_content"),
            patch.object(client, "_publish_via_editor", return_value={"url": "x"}),
        ):
            await client.create_and_publish("Title", "<p>Body</p>")

            # Default price is 300 (from config), no hashtags
            client._publish_via_editor.assert_called_once_with("nk1", 300, None)

    @pytest.mark.asyncio
    async def test_publish_no_hashtags(self, client: NoteClient) -> None:
        client._cookies = {"_note_session_v5": "abc"}

        with (
            patch.object(client, "_create_draft", return_value={"id": 1, "key": "nk1"}),
            patch.object(client, "_save_draft_content") as mock_save,
            patch.object(client, "_publish_via_editor", return_value={"url": "x"}),
        ):
            await client.create_and_publish("Title", "<p>Body</p>")

            mock_save.assert_called_once_with(
                1, "Title", "<p>Body</p>", None, eyecatch_src=None,
            )

    @pytest.mark.asyncio
    async def test_publish_draft_create_fails(self, client: NoteClient) -> None:
        """Error during draft creation raises NotePublishError."""
        client._cookies = {"_note_session_v5": "abc"}

        with patch.object(
            client, "_create_draft",
            side_effect=NotePublishError("下書き作成に失敗"),
        ):
            with pytest.raises(NotePublishError, match="下書き作成に失敗"):
                await client.create_and_publish("Title", "<p>Body</p>")

    @pytest.mark.asyncio
    async def test_publish_save_content_fails(self, client: NoteClient) -> None:
        """Error during content save raises NotePublishError."""
        client._cookies = {"_note_session_v5": "abc"}

        with (
            patch.object(client, "_create_draft", return_value={"id": 1, "key": "nk1"}),
            patch.object(
                client, "_save_draft_content",
                side_effect=NotePublishError("下書き保存に失敗"),
            ),
        ):
            with pytest.raises(NotePublishError, match="下書き保存に失敗"):
                await client.create_and_publish("Title", "<p>Body</p>")

    @pytest.mark.asyncio
    async def test_publish_editor_fails(self, client: NoteClient) -> None:
        """Error during editor publish wraps in NotePublishError with draft key."""
        client._cookies = {"_note_session_v5": "abc"}

        with (
            patch.object(client, "_create_draft", return_value={"id": 1, "key": "nk1"}),
            patch.object(client, "_save_draft_content"),
            patch.object(
                client, "_publish_via_editor",
                side_effect=Exception("editor crashed"),
            ),
        ):
            with pytest.raises(NotePublishError, match="nk1"):
                await client.create_and_publish("Title", "<p>Body</p>")


# ── get_status ────────────────────────────────────────────


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_status_no_session(self, client: NoteClient) -> None:
        status = await client.get_status()
        assert status["logged_in"] is False
        assert status["session_exists"] is False

    @pytest.mark.asyncio
    async def test_status_with_valid_session(self, client: NoteClient, tmp_session: Path) -> None:
        # Save a session first
        client._cookies = {"NOTE_SESSION_V5": "abc"}
        client._xsrf_token = "xyz"
        client._save_session()

        # Mock validation to return True
        with patch.object(client, "_is_session_valid", return_value=True):
            status = await client.get_status()
            assert status["logged_in"] is True
            assert status["session_exists"] is True
