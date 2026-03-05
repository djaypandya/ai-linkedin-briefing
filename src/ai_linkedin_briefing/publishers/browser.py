from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from ..exceptions import PublishError
from ..models import BrowserSessionResult, NewsletterDraft, PostDraft, PublishResult
from ..renderer import render_newsletter_markdown
from ..secrets_manager import load_linkedin_password


LINKEDIN_HOME_URL = "https://www.linkedin.com/feed/"
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LOGIN_EMAIL_SELECTOR = "#username"
LOGIN_PASSWORD_SELECTOR = "#password"
LOGIN_SUBMIT_SELECTOR = "button[type='submit']"
LOGIN_EMAIL_CANDIDATES = (
    "#username",
    "input[name='session_key']",
    "input[autocomplete='username']",
)
LOGIN_PASSWORD_CANDIDATES = (
    "#password",
    "input[name='session_password']",
    "input[autocomplete='current-password']",
)
SESSION_READY_SELECTOR = "nav.global-nav"
CHECKPOINT_MARKERS = (
    "checkpoint/challenge",
    "two-step-verification",
    "login-submit",
)
WRITE_ARTICLE_LINK_NAME = "Write an article on LinkedIn"
NEWSLETTER_NAME = "AI Morning Brief"
ARTICLE_EDITOR_SELECTOR = "[aria-label='Article editor content']"
ARTICLE_TITLE_SELECTOR = "[aria-label='Title']"
ARTICLE_EDITOR_CANDIDATES = (
    "[aria-label='Article editor content']",
    "[role='textbox'][aria-label*='Article']",
    "div[data-placeholder='Write here. You can also']",
)
ARTICLE_TITLE_CANDIDATES = (
    "[aria-label='Title']",
    "input[aria-label='Title']",
    "[role='textbox'][aria-label='Title']",
    "#article-editor-headline__textarea",
    "textarea.article-editor-headline__textarea",
    "textarea[placeholder='Title']",
)
NEXT_BUTTON_NAME = "Next"
PUBLISH_BUTTON_NAME = "Publish"
DISMISS_BUTTON_NAME = "Dismiss"
PUBLISH_POST_FIELD_SELECTOR = ".ql-clipboard"
PUBLISH_POST_FIELD_CANDIDATES = (
    ".ql-clipboard",
    ".ql-editor[contenteditable='true']",
    "[data-placeholder*='What do you want to talk about']",
    "[aria-label*='Text editor for creating content']",
)
DRAFT_SAVE_WAIT_MS = 10000
STEP_PAUSE_MS = 2000


@dataclass
class _BrowserSession:
    playwright: object
    browser: object
    context: object
    page: object


class LinkedInBrowserPublisher:
    def __init__(
        self,
        browser_state_path: Path,
        email: str | None,
        password: str | None,
        keychain_service: str = "ai-linkedin-briefing/linkedin",
    ) -> None:
        self.browser_state_path = browser_state_path
        self.email = email or ""
        self.keychain_service = keychain_service
        self.password = password or ""
        self.debug_dir = self.browser_state_path.parent / "debug"
        if not self.password and self.email:
            self.password = load_linkedin_password(self.email, self.keychain_service) or ""

    def ensure_session(self, headless: bool = True) -> BrowserSessionResult:
        self.browser_state_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PublishError(
                "Playwright is not installed in the current environment. Install dependencies before browser setup."
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = self._new_context(browser)
            page = context.new_page()

            try:
                page.goto(LINKEDIN_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                if self._requires_login(page):
                    if self.email and self.password:
                        self._perform_login(page, allow_manual_fallback=not headless)
                    else:
                        if headless:
                            raise PublishError(
                                "LinkedIn login is required. Provide credentials or run in headed mode for manual login."
                            )
                        self._wait_for_manual_login(page)
                self._assert_session_is_valid(page)
                context.storage_state(path=str(self.browser_state_path))
            except PlaywrightTimeoutError as exc:
                raise PublishError(f"Timed out while preparing the LinkedIn browser session: {exc}") from exc
            finally:
                context.close()
                browser.close()

        return BrowserSessionResult(
            success=True,
            detail="LinkedIn browser session prepared and saved.",
            state_path=str(self.browser_state_path),
        )

    def publish_newsletter(
        self,
        draft: NewsletterDraft,
        companion_post: PostDraft | None = None,
        headless: bool = True,
    ) -> PublishResult:
        newsletter_markdown = render_newsletter_markdown(draft)
        companion_post_text = companion_post.body if companion_post is not None else None
        return self.publish_newsletter_text(
            newsletter_markdown=newsletter_markdown,
            companion_post_text=companion_post_text,
            headless=headless,
        )

    def publish_newsletter_text(
        self,
        newsletter_markdown: str,
        companion_post_text: str | None = None,
        headless: bool = True,
    ) -> PublishResult:
        session = self._open_authenticated_session(headless=headless, target="newsletter")

        try:
            self._open_article_editor(session.page)
            title_text, body_text = self._split_newsletter_markdown(newsletter_markdown)
            self._fill_article_title(session.page, title_text)
            self._paste_article_body(session.page, body_text, title_text)
            self._open_publish_step(session.page)
            if companion_post_text is None:
                raise PublishError("Companion post text is required for the publish step.")
            self._fill_publish_post_text(session.page, companion_post_text)
            self._confirm_publish(session.page)
            return PublishResult(
                success=True,
                target="newsletter",
                detail="LinkedIn newsletter publish flow completed.",
            )
        finally:
            self._close_session(session)

    def publish_post(self, draft: PostDraft, headless: bool = True) -> PublishResult:
        return PublishResult(
            success=True,
            target="post",
            detail=(
                "Newsletter publish flow already used the companion post text in LinkedIn's publish dialog. "
                "A separate feed post flow has not been recorded yet."
            ),
        )

    def _open_article_editor(self, page) -> None:
        page.goto(LINKEDIN_HOME_URL, wait_until="domcontentloaded", timeout=30000)
        self._pause(page)
        self._assert_session_is_valid(page)
        page.get_by_role("link", name=WRITE_ARTICLE_LINK_NAME).click()
        self._pause(page)
        page.get_by_role("button", name=re.compile(NEWSLETTER_NAME)).click()
        self._pause(page)
        page.get_by_role("radio", name=NEWSLETTER_NAME).check()
        self._pause(page)
        self._click_button_if_present(page, "button", "Next")
        self._click_button_if_present(page, "button", "Continue")
        self._wait_for_any_locator(page, ARTICLE_EDITOR_CANDIDATES, timeout=30000)

    def _fill_article_title(self, page, title_text: str) -> None:
        title_locator = self._wait_for_first_locator_any_frame(
            page, ARTICLE_TITLE_CANDIDATES, timeout_ms=30000
        )
        if title_locator is None:
            self._save_debug_artifacts(page, "missing_title_field")
            raise PublishError("Could not find the LinkedIn article title field.")
        title_locator.click()
        self._pause(page)
        title_locator.fill(title_text.strip())
        self._pause(page)

    def _paste_article_body(self, page, body_text: str, expected_title: str) -> None:
        cleaned_body = body_text.strip()
        if not cleaned_body:
            raise PublishError("Newsletter body is empty after title extraction.")
        editor = self._first_present_locator_any_frame(page, ARTICLE_EDITOR_CANDIDATES)
        if editor is None:
            self._save_debug_artifacts(page, "missing_article_editor")
            raise PublishError("Could not find the LinkedIn article editor field.")
        sections = self._parse_markdown_story_sections(cleaned_body)
        if not sections:
            raise PublishError("Could not parse newsletter story sections from markdown body.")

        self._ensure_editor_focus(page, editor)
        editor.press("Meta+a")
        editor.press("Backspace")
        page.wait_for_timeout(200)
        for index, (headline, paragraph) in enumerate(sections):
            editor.press("Meta+b")
            editor.type(headline)
            editor.press("Meta+b")
            editor.press("Enter")
            editor.type(paragraph)
            if index < len(sections) - 1:
                editor.press("Enter")
                editor.press("Enter")
            self._pause(page, ms=300)

        page.wait_for_timeout(500)
        editor_text = editor.inner_text().strip()

        current_title = self._read_title_value(page).strip()
        if current_title != expected_title.strip():
            self._fill_article_title(page, expected_title)
            self._save_debug_artifacts(page, "title_was_modified_during_body_entry")

        missing_headings = [headline for headline, _ in sections if headline not in editor_text]
        if not editor_text or missing_headings:
            self._save_debug_artifacts(page, "empty_article_body_after_paste")
            raise PublishError(
                "LinkedIn article body formatting failed to apply correctly. "
                f"Missing headings: {missing_headings}"
            )
        # LinkedIn often needs a short delay to persist draft state before Next is enabled.
        page.wait_for_timeout(DRAFT_SAVE_WAIT_MS)

    def _open_publish_step(self, page) -> None:
        next_button = page.get_by_role("button", name=NEXT_BUTTON_NAME)
        if next_button.count() == 0:
            self._save_debug_artifacts(page, "missing_next_button")
            raise PublishError("Could not find the LinkedIn Next button after editor entry.")
        next_button.first.click()
        self._pause(page)
        post_field = self._wait_for_first_locator_any_frame(
            page, PUBLISH_POST_FIELD_CANDIDATES, timeout_ms=20000
        )
        if post_field is None:
            self._save_debug_artifacts(page, "missing_publish_modal_after_next")
            raise PublishError("Publish modal did not appear after clicking Next.")

    def _fill_publish_post_text(self, page, post_text: str) -> None:
        cleaned_post = post_text.strip()
        if not cleaned_post:
            raise PublishError("Companion post text is empty.")
        publish_field = self._wait_for_first_visible_locator_any_frame(
            page, PUBLISH_POST_FIELD_CANDIDATES, timeout_ms=10000
        )
        if publish_field is None:
            self._save_debug_artifacts(page, "missing_publish_post_field")
            raise PublishError("Could not find LinkedIn publish-dialog text field.")
        publish_field.click()
        publish_field.press("Meta+a")
        publish_field.type(cleaned_post)
        self._pause(page)

    def _confirm_publish(self, page) -> None:
        publish_button = page.get_by_role("button", name=PUBLISH_BUTTON_NAME)
        if publish_button.count() == 0:
            publish_button = page.locator("button:has-text('Publish')")
        if publish_button.count() == 0:
            self._save_debug_artifacts(page, "missing_publish_button")
            raise PublishError("Could not find a LinkedIn Publish button.")
        publish_button.first.click()
        self._pause(page)
        dismiss_button = page.get_by_role("button", name=DISMISS_BUTTON_NAME)
        if dismiss_button.count() > 0:
            try:
                dismiss_button.first.click(timeout=5000)
            except Exception:
                pass

    def _split_newsletter_markdown(self, markdown_text: str) -> tuple[str, str]:
        lines = markdown_text.splitlines()
        if not lines or not lines[0].startswith("# "):
            raise PublishError("Newsletter markdown must start with '# <date>' so the title can be derived.")
        title_text = lines[0][2:].strip()
        body_lines = lines[1:]
        body_text = "\n".join(body_lines).lstrip()
        return title_text, body_text

    def _parse_markdown_story_sections(self, body_text: str) -> list[tuple[str, str]]:
        lines = body_text.splitlines()
        sections: list[tuple[str, str]] = []
        current_headline: str | None = None
        current_paragraph_lines: list[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            headline_match = re.match(r"^\*\*(.+)\*\*$", line)
            if headline_match:
                if current_headline is not None:
                    paragraph = " ".join(part for part in current_paragraph_lines if part).strip()
                    if paragraph:
                        sections.append((current_headline, paragraph))
                current_headline = headline_match.group(1).strip()
                current_paragraph_lines = []
                continue

            if current_headline is not None:
                if line:
                    current_paragraph_lines.append(line)

        if current_headline is not None:
            paragraph = " ".join(part for part in current_paragraph_lines if part).strip()
            if paragraph:
                sections.append((current_headline, paragraph))

        return sections

    def _ensure_editor_focus(self, page, editor_locator) -> None:
        editor_locator.click()
        self._pause(page, ms=500)
        editor_locator.click()
        self._pause(page, ms=500)
        has_focus = editor_locator.evaluate(
            """element => {
                const active = document.activeElement;
                return active === element || element.contains(active);
            }"""
        )
        if not has_focus:
            raise PublishError("Could not focus LinkedIn article editor before paste.")

    def _read_title_value(self, page) -> str:
        title_locator = self._wait_for_first_locator_any_frame(
            page, ARTICLE_TITLE_CANDIDATES, timeout_ms=5000
        )
        if title_locator is None:
            return ""
        try:
            return title_locator.input_value()
        except Exception:
            return title_locator.inner_text()

    def _assert_ready(self) -> None:
        if not self.email:
            raise PublishError("LINKEDIN_EMAIL is required for browser publishing.")
        if not self.password:
            raise PublishError("LINKEDIN_PASSWORD is required for browser publishing.")

    def _wait_for_manual_login(self, page, timeout_seconds: int = 300) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._is_checkpoint_page(page):
                raise PublishError(
                    "LinkedIn presented a checkpoint or verification flow during manual login."
                )
            if not self._requires_login(page):
                return
            page.wait_for_timeout(2000)
        raise PublishError(
            "Timed out waiting for manual LinkedIn login. Run session setup again and complete login in the browser."
        )

    def _new_context(self, browser):
        if self.browser_state_path.exists():
            return browser.new_context(storage_state=str(self.browser_state_path))
        return browser.new_context()

    def _open_authenticated_session(self, headless: bool, target: str) -> _BrowserSession:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PublishError(
                "Playwright is not installed in the current environment. Install dependencies before publishing."
            ) from exc

        playwright_context = sync_playwright().start()
        browser = playwright_context.chromium.launch(headless=headless)
        context = self._new_context(browser)
        page = context.new_page()
        session = _BrowserSession(
            playwright=playwright_context,
            browser=browser,
            context=context,
            page=page,
        )

        try:
            page.goto(LINKEDIN_HOME_URL, wait_until="domcontentloaded", timeout=30000)
            if self._requires_login(page):
                if self.email and self.password:
                    self._perform_login(page, allow_manual_fallback=not headless)
                    context.storage_state(path=str(self.browser_state_path))
                else:
                    raise PublishError(
                        f"LinkedIn session is not authenticated for {target} publishing and no credentials are configured."
                    )
            self._assert_session_is_valid(page)
            return session
        except PlaywrightTimeoutError as exc:
            self._close_session(session)
            raise PublishError(f"Timed out while opening LinkedIn for {target} publishing: {exc}") from exc
        except Exception:
            self._close_session(session)
            raise

    def _close_session(self, session: _BrowserSession) -> None:
        try:
            session.context.close()
        finally:
            try:
                session.browser.close()
            finally:
                session.playwright.stop()

    def _perform_login(self, page, allow_manual_fallback: bool) -> None:
        page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        email_locator = self._first_present_locator(page, LOGIN_EMAIL_CANDIDATES)
        password_locator = self._first_present_locator(page, LOGIN_PASSWORD_CANDIDATES)
        if email_locator is None or password_locator is None:
            if allow_manual_fallback:
                self._wait_for_manual_login(page)
                return
            raise PublishError("LinkedIn login fields were not found.")

        email_locator.fill(self.email)
        password_locator.fill(self.password)
        submit_locator = page.locator(LOGIN_SUBMIT_SELECTOR)
        if submit_locator.count() > 0:
            submit_locator.first.click()
        else:
            password_locator.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        if self._is_checkpoint_page(page):
            raise PublishError(
                "LinkedIn presented a checkpoint or verification flow. Manual intervention is required."
            )

    def _first_present_locator(self, page, selectors: tuple[str, ...]):
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() > 0:
                return locator.first
        return None

    def _first_present_locator_any_frame(self, page, selectors: tuple[str, ...]):
        locator = self._first_present_locator(page, selectors)
        if locator is not None:
            return locator
        for frame in page.frames:
            for selector in selectors:
                frame_locator = frame.locator(selector)
                if frame_locator.count() > 0:
                    return frame_locator.first
        return None

    def _wait_for_first_locator_any_frame(self, page, selectors: tuple[str, ...], timeout_ms: int):
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            locator = self._first_present_locator_any_frame(page, selectors)
            if locator is not None:
                return locator
            page.wait_for_timeout(500)
        return None

    def _wait_for_first_visible_locator_any_frame(self, page, selectors: tuple[str, ...], timeout_ms: int):
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            for selector in selectors:
                locator = page.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    return locator.first
            for frame in page.frames:
                for selector in selectors:
                    locator = frame.locator(selector)
                    if locator.count() > 0 and locator.first.is_visible():
                        return locator.first
            page.wait_for_timeout(500)
        return None

    def _wait_for_any_locator(self, page, selectors: tuple[str, ...], timeout: int) -> None:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                locator.first.wait_for(timeout=timeout)
                return
            except Exception:
                continue
        for frame in page.frames:
            for selector in selectors:
                locator = frame.locator(selector)
                try:
                    locator.first.wait_for(timeout=2000)
                    return
                except Exception:
                    continue
        self._save_debug_artifacts(page, "missing_editor_controls")
        raise PublishError("Could not find expected LinkedIn editor controls after newsletter selection.")

    def _click_button_if_present(self, page, role: str, name: str) -> None:
        button = page.get_by_role(role, name=name)
        if button.count() > 0:
            button.first.click()
            self._pause(page)

    def _save_debug_artifacts(self, page, label: str) -> None:
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            screenshot_path = self.debug_dir / f"{stamp}_{label}.png"
            html_path = self.debug_dir / f"{stamp}_{label}.html"
            page.screenshot(path=str(screenshot_path), full_page=True)
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            return

    def _pause(self, page, ms: int = STEP_PAUSE_MS) -> None:
        page.wait_for_timeout(ms)

    def _requires_login(self, page) -> bool:
        if page.locator(LOGIN_EMAIL_SELECTOR).count() > 0:
            return True
        current_url = page.url.lower()
        return "linkedin.com/login" in current_url or "/uas/login" in current_url

    def _is_checkpoint_page(self, page) -> bool:
        current_url = page.url.lower()
        return any(marker in current_url for marker in CHECKPOINT_MARKERS)

    def _assert_session_is_valid(self, page) -> None:
        if self._is_checkpoint_page(page):
            raise PublishError(
                "LinkedIn session hit a checkpoint or verification page. Browser automation cannot continue safely."
            )

        current_url = page.url.lower()
        if "linkedin.com/login" in current_url or "/uas/login" in current_url:
            raise PublishError("LinkedIn redirected to login. Saved browser session is not valid.")

        if "linkedin.com" not in current_url:
            raise PublishError(f"Unexpected LinkedIn navigation target: {page.url}")

        if page.locator(SESSION_READY_SELECTOR).count() == 0:
            if "linkedin.com/feed" in current_url or "linkedin.com/newsletters" in current_url:
                return
            if "/in/" in current_url or "/mynetwork/" in current_url or "/jobs/" in current_url:
                return
