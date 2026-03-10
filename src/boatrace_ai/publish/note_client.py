"""note.com client: authentication via Playwright, article publishing via hybrid approach.

Authentication flow:
    1. Playwright opens note.com/login, fills email/password, clicks submit
    2. All cookies are extracted from the browser context
    3. Cookies are saved to disk for reuse

Publishing flow (hybrid API + Playwright):
    1. POST /api/v1/text_notes — create draft
    2. POST /api/v1/text_notes/draft_save — save title, body, hashtags
    3. Playwright opens editor.note.com/notes/{key}/edit/ to publish
    4. Editor handles the correct internal format for publishing

Note: This uses note.com's unofficial API which may change without notice.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

from boatrace_ai import config

log = logging.getLogger(__name__)

NOTE_BASE_URL = "https://note.com"
NOTE_EDITOR_BASE = "https://editor.note.com"
NOTE_API_URL = f"{NOTE_BASE_URL}/api/v1/text_notes"
NOTE_UPLOAD_URL = f"{NOTE_BASE_URL}/api/v1/uploads/image"
NOTE_LOGIN_URL = f"{NOTE_BASE_URL}/login"

# Confirmed login form selectors (verified from NoteClient OSS project)
LOGIN_EMAIL_SELECTOR = "#email"
LOGIN_PASSWORD_SELECTOR = "#password"
LOGIN_BUTTON_SELECTOR = ".o-login__button button"

# Editor selectors
EDITOR_TITLE_SELECTOR = "textarea"
EDITOR_BODY_SELECTOR = ".ProseMirror"

# Common headers for API calls
API_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

# User agent for Playwright
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class NoteAuthError(Exception):
    """Raised when note.com authentication fails."""


class NotePublishError(Exception):
    """Raised when article publishing fails."""


class NoteClient:
    """Client for note.com: handles login, session management, and article publishing."""

    def __init__(self, session_path: Path | None = None) -> None:
        self._session_path = session_path or config.NOTE_SESSION_PATH
        self._cookies: dict[str, str] = {}
        self._xsrf_token: str = ""
        # Shared browser lifecycle (optional, for batch publishing)
        self._playwright: object | None = None
        self._browser: object | None = None
        self._browser_context: object | None = None

    async def open_browser(self) -> None:
        """Launch a shared Playwright browser for reuse across multiple publishes."""
        if self._browser_context is not None:
            return  # Already open
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise NotePublishError("playwright が必要です")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._browser_context = await self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
        )
        # Set cookies for authentication
        if self._cookies:
            cookie_list = [
                {"name": name, "value": value, "domain": ".note.com", "path": "/"}
                for name, value in self._cookies.items()
            ]
            await self._browser_context.add_cookies(cookie_list)
        log.info("Shared browser opened for batch publishing")

    async def close_browser(self) -> None:
        """Close the shared Playwright browser."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
            self._browser_context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        log.info("Shared browser closed")

    async def __aenter__(self) -> "NoteClient":
        await self.open_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_browser()

    def _save_session(self) -> None:
        """Persist session cookies to disk."""
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"cookies": self._cookies, "xsrf_token": self._xsrf_token}
        self._session_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        log.info("Session saved to %s", self._session_path)

    def _load_session(self) -> bool:
        """Load session cookies from disk. Returns True if loaded."""
        if not self._session_path.exists():
            log.debug("No session file found at %s", self._session_path)
            return False
        try:
            data = json.loads(self._session_path.read_text())
            self._cookies = data["cookies"]
            self._xsrf_token = data["xsrf_token"]
            log.info("Session loaded from %s", self._session_path)
            return True
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Failed to load session: %s", e)
            return False

    async def _is_session_valid(self) -> bool:
        """Check if the current session cookies are still valid."""
        if not self._cookies:
            return False
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
                for path in ("/api/v1/stats/pv_count", "/api/v2/creators/mine"):
                    resp = await client.get(
                        f"{NOTE_BASE_URL}{path}",
                        cookies=self._cookies,
                        headers=API_HEADERS,
                    )
                    if resp.status_code == 200:
                        return True
                    if resp.status_code == 401:
                        return False
                return False
        except httpx.HTTPError as e:
            log.warning("Session validation failed: %s", e)
            return False

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        return {**API_HEADERS}

    async def _check_captcha_required(self) -> bool:
        """Check if note.com requires CAPTCHA for login (rate limiting)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{NOTE_BASE_URL}/api/v3/challenges?via=login")
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    challenges = data.get("challenges", [])
                    if challenges:
                        log.warning("CAPTCHA required: %s", challenges)
                        return True
            return False
        except Exception:
            return False

    async def login(self) -> None:
        """Login to note.com using Playwright and save session cookies.

        Raises NoteAuthError if login fails or CAPTCHA is required.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise NoteAuthError(
                "playwright がインストールされていません。\n"
                "pip install playwright && playwright install chromium"
            )

        config.validate_note()

        # Check for CAPTCHA (Playwright handles invisible reCAPTCHA automatically)
        if await self._check_captcha_required():
            log.info("CAPTCHA detected, but Playwright handles invisible reCAPTCHA")

        log.info("Starting Playwright login to note.com...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="ja-JP",
                )
                page = await context.new_page()

                # Visit homepage first to establish cookies
                await page.goto(NOTE_BASE_URL)
                await asyncio.sleep(2)

                await page.goto(NOTE_LOGIN_URL)
                await page.wait_for_load_state("networkidle")
                await page.wait_for_selector(LOGIN_EMAIL_SELECTOR, timeout=10000)

                # Type credentials with delay (avoids CAPTCHA triggering)
                await page.click(LOGIN_EMAIL_SELECTOR)
                await page.keyboard.type(config.NOTE_EMAIL, delay=50)
                await asyncio.sleep(0.5)
                await page.click(LOGIN_PASSWORD_SELECTOR)
                await page.keyboard.type(config.NOTE_PASSWORD, delay=50)
                await asyncio.sleep(1)

                await page.click(LOGIN_BUTTON_SELECTOR)

                try:
                    await page.wait_for_url(
                        lambda url: url != NOTE_LOGIN_URL and "login" not in url,
                        timeout=15000,
                    )
                except Exception:
                    if "login" in page.url:
                        raise NoteAuthError(
                            "ログインに失敗しました。メールアドレスとパスワードを確認してください。"
                        )

                await page.wait_for_load_state("networkidle")

                # Extract ALL cookies
                cookies = await context.cookies()
                self._cookies = {}
                self._xsrf_token = ""

                for cookie in cookies:
                    if cookie.get("domain", "").endswith("note.com"):
                        self._cookies[cookie["name"]] = cookie["value"]

                    name_lower = cookie["name"].lower()
                    if "xsrf" in name_lower or "csrf" in name_lower:
                        self._xsrf_token = cookie["value"]

                if not self._cookies:
                    raise NoteAuthError(
                        "ログイン後にcookieを取得できませんでした。\n"
                        "note.comのログインページ構造が変更された可能性があります。"
                    )

                log.info(
                    "Login successful. Cookies: %s",
                    ", ".join(sorted(self._cookies.keys())),
                )

                self._save_session()

            finally:
                await browser.close()

    async def ensure_logged_in(self) -> None:
        """Ensure we have a valid session, logging in if necessary."""
        if self._load_session() and await self._is_session_valid():
            log.info("Existing session is valid")
            return
        log.info("Session invalid or missing, logging in...")
        await self.login()

    async def upload_image(self, image_path: Path) -> str:
        """Upload image to note.com and return the image URL.

        Args:
            image_path: Path to the image file to upload.

        Returns:
            The URL of the uploaded image.

        Raises:
            NotePublishError: If upload fails.
        """
        if not image_path.exists():
            raise NotePublishError(f"画像ファイルが見つかりません: {image_path}")

        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            with open(image_path, "rb") as f:
                files = {"file": (image_path.name, f, "image/png")}
                headers = {"X-Requested-With": "XMLHttpRequest"}
                resp = await client.post(
                    NOTE_UPLOAD_URL,
                    files=files,
                    cookies=self._cookies,
                    headers=headers,
                )
            if resp.status_code not in (200, 201):
                raise NotePublishError(
                    f"画像アップロードに失敗しました (HTTP {resp.status_code}): {resp.text[:200]}"
                )
            data = resp.json().get("data", {})
            image_url = data.get("url") or data.get("src") or ""
            if not image_url:
                raise NotePublishError(f"画像URLの取得に失敗しました: {data}")
            log.info("Image uploaded: %s", image_url)
            return image_url

    async def _create_draft(self) -> dict:
        """Create a new draft article via API.

        Returns:
            Dict with 'id' and 'key' of the created draft.
        """
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            resp = await client.post(
                NOTE_API_URL,
                json={"template_key": None},
                cookies=self._cookies,
                headers=self._build_headers(),
            )
            if resp.status_code not in (200, 201):
                raise NotePublishError(
                    f"下書き作成に失敗しました (HTTP {resp.status_code}): {resp.text[:200]}"
                )
            data = resp.json().get("data", {})
            draft_id = data.get("id")
            draft_key = data.get("key")
            if not draft_id or not draft_key:
                raise NotePublishError(f"下書きIDの取得に失敗しました: {data}")
            log.info("Draft created: id=%s, key=%s", draft_id, draft_key)
            return {"id": draft_id, "key": draft_key}

    async def _save_draft_content(
        self,
        draft_id: int,
        title: str,
        html_body: str,
        hashtags: list[str] | None = None,
    ) -> None:
        """Save content to draft via draft_save API."""
        payload: dict[str, object] = {
            "name": title,
            "body": html_body,
        }
        if hashtags:
            payload["hashtags"] = hashtags

        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{NOTE_API_URL}/draft_save?id={draft_id}",
                json=payload,
                cookies=self._cookies,
                headers=self._build_headers(),
            )
            if resp.status_code not in (200, 201):
                raise NotePublishError(
                    f"下書き保存に失敗しました (HTTP {resp.status_code}): {resp.text[:200]}"
                )
            log.info("Draft content saved (id=%s)", draft_id)

    async def _publish_via_editor(
        self,
        draft_key: str,
        price: int,
        hashtags: list[str] | None = None,
        eyecatch_path: Path | None = None,
    ) -> dict:
        """Publish a draft article using the Playwright editor.

        Flow (verified against live note.com):
        1. Open editor.note.com/notes/{key}/edit/
        2. Click "公開に進む" button → navigates to /notes/{key}/publish/
        3. On publish settings page: set eyecatch, hashtags, paid settings
        4. Click "投稿する" button to finalize

        Returns:
            Dict with publish result info.
        """
        editor_url = f"{NOTE_EDITOR_BASE}/notes/{draft_key}/edit/"
        log.info("Opening editor: %s", editor_url)

        result: dict[str, object] = {}

        # Decide whether to use the shared browser or launch a standalone one
        shared = self._browser_context is not None
        context = self._browser_context
        standalone_pw = None
        standalone_browser = None

        if not shared:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                raise NotePublishError("playwright が必要です")

            standalone_pw = await async_playwright().start()
            standalone_browser = await standalone_pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = await standalone_browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
                locale="ja-JP",
            )
            # Set cookies for authentication
            cookie_list = [
                {"name": name, "value": value, "domain": ".note.com", "path": "/"}
                for name, value in self._cookies.items()
            ]
            await context.add_cookies(cookie_list)

        try:
            page = await context.new_page()

            # Capture publish API responses
            publish_response: dict = {}

            async def on_response(response):
                url = response.url
                if "/api/" in url and ("text_notes" in url or "notes" in url):
                    method = response.request.method
                    status = response.status
                    if method in ("PUT", "POST") and status in (200, 201):
                        try:
                            body = await response.json()
                            publish_response["status"] = status
                            publish_response["data"] = body
                            publish_response["url"] = url
                        except Exception:
                            pass

            page.on("response", on_response)

            # Navigate to editor
            await page.goto(editor_url)
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # Verify editor loaded (ProseMirror contenteditable div)
            try:
                await page.wait_for_selector(EDITOR_BODY_SELECTOR, timeout=15000)
            except Exception:
                raise NotePublishError(
                    "エディタが読み込めませんでした。セッションが無効かもしれません。"
                )

            log.info("Editor loaded with content")

            # Step 1: Set eyecatch image in editor (before publish)
            if eyecatch_path and eyecatch_path.exists():
                await self._set_eyecatch_in_editor(page, eyecatch_path)

            # Step 2: Click "公開に進む" button (in editor header)
            publish_btn = await self._find_button(
                page, ["公開に進む", "公開設定", "公開"]
            )
            if not publish_btn:
                raise NotePublishError(
                    "公開ボタンが見つかりませんでした。エディタUIが変更された可能性があります。"
                )

            await publish_btn.click()
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            log.info("Navigated to publish page: %s", page.url)

            # Step 3: Set hashtags on publish settings page
            if hashtags:
                await self._set_hashtags(page, hashtags)

            # Step 4: Set paid article settings if price > 0
            if price > 0:
                await self._set_paid_settings(page, price)

            # Step 5: Click "投稿する" button (final publish)
            final_btn = await self._find_button(
                page, ["投稿する", "投稿", "公開する", "公開"]
            )
            if not final_btn:
                raise NotePublishError(
                    "投稿ボタンが見つかりませんでした。公開設定UIが変更された可能性があります。"
                )

            await final_btn.click()
            await asyncio.sleep(5)
            log.info("Final publish clicked. URL: %s", page.url)

            # Extract result from PUT response
            result["draft_key"] = draft_key
            if publish_response:
                result["api_response"] = publish_response
                # Extract user urlname from PUT response to build note URL
                put_data = publish_response.get("data", {})
                if isinstance(put_data, dict):
                    data_inner = put_data.get("data", put_data)
                    user = data_inner.get("user", {})
                    urlname = user.get("urlname", "")
                    key = data_inner.get("key", draft_key)
                    if urlname:
                        result["note_url"] = f"{NOTE_BASE_URL}/{urlname}/n/{key}"
                    else:
                        result["note_url"] = f"{NOTE_BASE_URL}/n/{key}"

            if "note_url" not in result:
                result["note_url"] = f"{NOTE_BASE_URL}/n/{draft_key}"

            log.info("Publish complete. note_url=%s", result.get("note_url"))

            # Close the page to free resources (but keep context alive for shared mode)
            await page.close()

        finally:
            if not shared:
                if standalone_browser is not None:
                    await standalone_browser.close()
                if standalone_pw is not None:
                    await standalone_pw.stop()

        return result

    async def _set_eyecatch_in_editor(self, page, eyecatch_path: Path) -> None:
        """Set eyecatch image via the editor page.

        Strategy: Set up MutationObserver to capture dynamically created file inputs,
        then click the eyecatch button. The button creates a transient <input type="file">,
        clicks it (opening file dialog), then removes it. We intercept this by:
        1. Monkey-patching HTMLInputElement.click to prevent the native dialog
        2. Capturing the dynamically created input
        3. Setting files on it via Playwright
        """
        try:
            eyecatch_btn = page.locator('button[aria-label="画像を追加"]')
            if await eyecatch_btn.count() == 0:
                log.warning("[eyecatch] ボタンが見つかりません。スキップ")
                return

            # Install interceptor: monkey-patch input.click() to prevent native dialog
            # and capture the dynamically created file input
            await page.evaluate("""() => {
                window.__eyecatchInputCaptured = null;
                const origClick = HTMLInputElement.prototype.click;
                HTMLInputElement.prototype.click = function() {
                    if (this.type === 'file') {
                        window.__eyecatchInputCaptured = this;
                        // Don't call origClick - prevent native dialog
                        // Keep the input in DOM so Playwright can set files
                        if (!this.parentElement) {
                            this.style.display = 'none';
                            document.body.appendChild(this);
                        }
                        return;
                    }
                    return origClick.call(this);
                };
            }""")
            log.warning("[eyecatch] Installed input.click interceptor")

            # Click the eyecatch button - this should trigger the interceptor
            await eyecatch_btn.first.click()
            await asyncio.sleep(2)

            # Check if we captured a file input
            captured = await page.evaluate("""() => {
                const inp = window.__eyecatchInputCaptured;
                if (!inp) return null;
                return {
                    type: inp.type,
                    accept: inp.accept || '',
                    inDOM: !!inp.parentElement,
                    id: inp.id || '_no_id',
                };
            }""")
            log.warning("[eyecatch] Captured input: %s", json.dumps(captured, ensure_ascii=False) if captured else "null")

            if captured:
                # Set a unique ID so we can target it with Playwright
                await page.evaluate("""() => {
                    const inp = window.__eyecatchInputCaptured;
                    inp.id = '_pw_eyecatch_file';
                }""")
                pw_input = page.locator('#_pw_eyecatch_file')
                await pw_input.set_input_files(str(eyecatch_path))
                await asyncio.sleep(3)

                # Dispatch change event to trigger the upload handler
                await page.evaluate("""() => {
                    const inp = window.__eyecatchInputCaptured;
                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                }""")
                await asyncio.sleep(4)
                log.warning("[eyecatch] File set + change dispatched")

                # Handle CropModal
                await self._handle_crop_modal(page)
                log.warning("[eyecatch] Eyecatch image set: %s", eyecatch_path.name)
            else:
                # Fallback: try expect_file_chooser directly
                log.warning("[eyecatch] No captured input. Trying expect_file_chooser...")
                try:
                    # Restore original click first
                    await page.evaluate("""() => {
                        delete HTMLInputElement.prototype.click;
                    }""")
                    async with page.expect_file_chooser(timeout=8000) as fc_info:
                        await eyecatch_btn.first.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(str(eyecatch_path))
                    await asyncio.sleep(4)
                    await self._handle_crop_modal(page)
                    log.warning("[eyecatch] Set via file chooser fallback")
                except Exception as e:
                    log.warning("[eyecatch] All strategies failed: %s", e)

            # Restore original click
            await page.evaluate("""() => {
                delete HTMLInputElement.prototype.click;
            }""")

        except Exception as e:
            log.warning("[eyecatch] 設定失敗（投稿は続行）: %s", e)
            # Restore original click on error
            try:
                await page.evaluate("() => { delete HTMLInputElement.prototype.click; }")
            except Exception:
                pass

            # Step 3: Handle CropModal that appears after image upload
            # note.com shows a React modal with class "CropModal__overlay"
            # We need to find and click the confirm/apply button in the modal
            await self._handle_crop_modal(page)

            log.info("Eyecatch image set: %s", eyecatch_path.name)

        except Exception as e:
            log.warning("アイキャッチ画像の設定に失敗（投稿は続行）: %s", e)

    async def _handle_crop_modal(self, page) -> None:
        """Handle the CropModal that appears after uploading an eyecatch image.

        The modal has class 'CropModal__overlay' and contains confirm/apply buttons.
        We click the confirm button to apply the crop and close the modal.
        """
        # Wait for crop modal to appear
        modal = page.locator('.ReactModal__Overlay, [class*="CropModal"]')
        try:
            await modal.first.wait_for(state="visible", timeout=5000)
            log.info("CropModal detected, looking for confirm button...")
        except Exception:
            log.info("No CropModal appeared, continuing...")
            return

        await asyncio.sleep(1)

        # Try multiple button text options for the confirm button
        confirm_texts = ["適用", "完了", "保存", "OK", "決定", "確定", "設定"]
        for text in confirm_texts:
            btn = page.locator(f'.ReactModal__Content button:has-text("{text}")')
            if await btn.count() > 0 and await btn.first.is_visible():
                log.info("Clicking CropModal confirm button: '%s'", text)
                await btn.first.click()
                await asyncio.sleep(2)
                return

        # Fallback: click any visible button inside the modal content
        modal_buttons = page.locator('.ReactModal__Content button')
        count = await modal_buttons.count()
        log.info("CropModal has %d buttons", count)
        for i in range(count):
            btn = modal_buttons.nth(i)
            if await btn.is_visible():
                text = (await btn.text_content() or "").strip()
                log.info("CropModal button[%d]: '%s'", i, text)
                # Skip cancel/close buttons
                if any(w in text for w in ["キャンセル", "閉じる", "戻る", "×"]):
                    continue
                log.info("Clicking CropModal button: '%s'", text)
                await btn.first.click()
                await asyncio.sleep(2)
                return

        # Last resort: press Escape to dismiss
        log.warning("CropModal confirm button not found, pressing Escape")
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)

    async def _find_button(self, page, text_options: list[str]):
        """Find a visible button by text content, trying multiple options."""
        for text in text_options:
            try:
                btn = page.get_by_role("button", name=text)
                if await btn.count() > 0 and await btn.first.is_visible():
                    log.debug("Found button: '%s'", text)
                    return btn.first
            except Exception:
                pass

        # Fallback: search all visible buttons for partial match
        buttons = await page.query_selector_all("button")
        for btn in buttons:
            if await btn.is_visible():
                btn_text = (await btn.text_content() or "").strip()
                for text in text_options:
                    if text in btn_text:
                        log.debug("Found button (fallback): '%s'", btn_text)
                        return btn
        return None

    async def _set_hashtags(self, page, hashtags: list[str]) -> None:
        """Set hashtags on the publish settings page.

        The publish page has a "ハッシュタグ" tab and an input with
        placeholder "ハッシュタグを追加する". Type each tag and press Enter.
        """
        try:
            # Click "ハッシュタグ" tab to ensure it's active
            tag_tab = await self._find_button(page, ["ハッシュタグ"])
            if tag_tab:
                await tag_tab.click()
                await asyncio.sleep(1)

            # Find the hashtag input
            inp = await page.query_selector('input[placeholder="ハッシュタグを追加する"]')
            if not inp:
                log.warning("Hashtag input not found")
                return

            for tag in hashtags:
                await inp.click()
                await inp.fill(tag)
                await asyncio.sleep(0.3)
                await inp.press("Enter")
                await asyncio.sleep(0.5)
                log.debug("Added hashtag: %s", tag)

            log.info("Set %d hashtags", len(hashtags))

        except Exception as e:
            log.warning("Failed to set hashtags: %s", e)

    async def _set_paid_settings(self, page, price: int) -> None:
        """Set paid article settings on the publish settings page.

        Flow (verified against live note.com):
        1. Click "記事タイプ" tab to show free/paid options
        2. Click "有料" option
        3. Set price in the price input field

        This is best-effort — if the UI elements aren't found, we log a warning
        and continue (the article will be published as free).
        """
        try:
            # Click "記事タイプ" tab to reveal free/paid options
            type_tab = await self._find_button(page, ["記事タイプ"])
            if type_tab:
                await type_tab.click()
                await asyncio.sleep(1)
                log.info("Clicked '記事タイプ' tab")
            else:
                log.warning("'記事タイプ' tab not found")

            # Look for "有料" option (button, radio, or label)
            paid_clicked = False
            for selector in [
                "button:has-text('有料')",
                "text=有料",
                "label:has-text('有料')",
                "[role='radio']:has-text('有料')",
            ]:
                try:
                    el = await page.query_selector(selector)
                    if el and await el.is_visible():
                        await el.click()
                        await asyncio.sleep(1)
                        paid_clicked = True
                        log.info("Clicked paid option: %s", selector)
                        break
                except Exception:
                    pass

            if not paid_clicked:
                log.warning("有料 option not found — article will be free")
                return

            # Find and set price input
            price_set = False
            inputs = await page.query_selector_all("input")
            for inp in inputs:
                if await inp.is_visible():
                    inp_type = await inp.get_attribute("type") or ""
                    placeholder = await inp.get_attribute("placeholder") or ""
                    if inp_type == "number" or "円" in placeholder or "価格" in placeholder:
                        await inp.click()
                        await inp.fill(str(price))
                        await asyncio.sleep(0.5)
                        price_set = True
                        log.info("Price set to ¥%d", price)
                        break

            if not price_set:
                log.warning("Price input not found — price may not be set")

        except Exception as e:
            log.warning("Failed to set paid settings: %s", e)

    async def create_and_publish(
        self,
        title: str,
        html_body: str,
        price: int | None = None,
        hashtags: list[str] | None = None,
        eyecatch_title: str | None = None,
        article_type: str | None = None,
    ) -> dict:
        """Create and publish a paid article on note.com.

        Uses hybrid approach:
        1. API to create draft and save content (fast)
        2. Playwright to publish via editor (handles format correctly)

        Args:
            title: Article title
            html_body: HTML body content (with <pay> tag for paid section)
            price: Price in JPY (default: config.NOTE_ARTICLE_PRICE)
            hashtags: List of hashtag strings
            eyecatch_title: Title text for the OGP eyecatch image.
                If provided, an eyecatch image is generated and uploaded.
            article_type: Article type for eyecatch icon
                (prediction, grades, results, midday, track_record, membership).

        Returns:
            Dict containing publish result info.

        Raises:
            NotePublishError: If publishing fails.
        """
        if price is None:
            price = config.NOTE_ARTICLE_PRICE

        log.info("Publishing article: %s (¥%d)", title, price)

        # Step 0: Generate eyecatch image (optional, best-effort)
        eyecatch_path: Path | None = None
        if eyecatch_title:
            eyecatch_path = await self._generate_eyecatch_image(
                eyecatch_title, article_type or "prediction"
            )

        # Step 0.5: Upload eyecatch via API and embed in HTML as fallback
        # note.com uses the first image in the article body as OGP if no eyecatch is set
        if eyecatch_path:
            try:
                eyecatch_url = await self.upload_image(eyecatch_path)
                html_body = (
                    f'<p><img src="{eyecatch_url}" alt="{eyecatch_title}"></p>\n'
                    + html_body
                )
                log.info("Eyecatch embedded in HTML body: %s", eyecatch_url)
            except Exception as e:
                log.warning("アイキャッチ画像のアップロードに失敗: %s", e)

        # Step 1: Create draft via API
        draft = await self._create_draft()

        # Step 2: Save content via API
        await self._save_draft_content(
            draft["id"], title, html_body, hashtags
        )

        # Step 3: Publish via Playwright editor (eyecatch set in editor page)
        try:
            result = await self._publish_via_editor(
                draft["key"], price, hashtags, eyecatch_path=eyecatch_path
            )
        except Exception as e:
            log.error("Playwright publish failed: %s", e)
            raise NotePublishError(
                f"記事の公開に失敗しました: {e}\n"
                f"下書きは保存されています (key={draft['key']})"
            ) from e
        finally:
            # Clean up eyecatch temp file
            if eyecatch_path:
                try:
                    eyecatch_path.unlink(missing_ok=True)
                    eyecatch_path.parent.rmdir()
                except OSError:
                    pass

        return result

    async def _generate_eyecatch_image(
        self, eyecatch_title: str, article_type: str
    ) -> Path | None:
        """Generate an eyecatch image and return the file path.

        Returns the image path or None if generation fails.
        Failures are logged but do not raise exceptions.
        """
        try:
            from boatrace_ai.publish.eyecatch import generate_eyecatch

            image_path = await generate_eyecatch(eyecatch_title, article_type)
            return image_path
        except Exception as e:
            log.warning("アイキャッチ画像の生成に失敗（記事投稿は続行）: %s", e)
            return None

    async def get_status(self) -> dict[str, object]:
        """Check login status and return session info."""
        session_exists = self._session_path.exists()
        loaded = self._load_session() if session_exists else False
        valid = await self._is_session_valid() if loaded else False
        return {
            "logged_in": valid,
            "session_path": str(self._session_path),
            "session_exists": session_exists,
        }
