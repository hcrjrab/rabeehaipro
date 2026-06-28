"""Browser tools (Playwright) — search, navigate, extract, screenshot, export.

A self-contained Playwright session manager backs these tools. A single
browser instance is shared across calls (lazy-started) for performance, with
one page per logical "tab". The browser is closed on app shutdown.

Safety
------
- ``web.search`` / ``web.fetch`` / ``web.extract`` are read-only (NONE risk).
- ``web.fill_form`` writes to a page (SAFE — reversible).
- ``web.click`` can trigger navigation/submission (DESTRUCTIVE — gated).
- Authentication uses the user's own credentials via stored profiles; the
  agent never asks for or stores passwords. Credential handling lands in
  Phase 6's RBAC/secret work.

Playwright is imported lazily; tools are skipped at registry time if absent.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext

_log = logging.getLogger(__name__)

# Module-level browser manager so a single Chromium instance is reused.
_browser_manager: _BrowserManager | None = None


class _BrowserManager:
    """Owns a single Playwright browser + context for the process lifetime.

    Kept as a separate class so it can be reset cleanly between tests and so
    the tools below share state without globals scattered everywhere.
    """

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None  # the single active tab

    async def _ensure(self) -> Any:
        """Lazy-start Playwright + a headed/headless Chromium."""
        if self._page is not None:
            return self._page
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ImportError(
                "Playwright is required. pip install playwright && playwright install"
            ) from exc

        self._playwright = await async_playwright().start()
        # Headless by default for automation safety; flip via env in Phase 7.
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) RabeehAgentPro/0.1"),
        )
        self._page = await self._context.new_page()
        _log.info("Playwright browser started (headless).")
        return self._page

    @property
    def page(self) -> Any:
        """Return the active page (raises if not started — call within async)."""
        return self._page

    async def close(self) -> None:
        """Tear down browser, context, and playwright in the right order."""
        import contextlib

        for resource in (self._page, self._context, self._browser):
            if resource is not None:
                with contextlib.suppress(Exception):
                    await resource.close()
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None


def get_browser_manager() -> _BrowserManager:
    """Return the shared browser manager singleton."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = _BrowserManager()
    return _browser_manager


async def close_browser() -> None:
    """Close the shared browser (shutdown / tests)."""
    global _browser_manager
    if _browser_manager is not None:
        await _browser_manager.close()
    _browser_manager = None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class _BrowserTool(BaseTool):
    """Shared base: ensure the browser is up, then delegate to ``_do``."""

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        try:
            page = await get_browser_manager()._ensure()
            return await self._do(args, ctx, page)
        except ImportError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except Exception as exc:
            _log.warning("Browser tool failed: %s", exc)
            return ToolCallResult(ok=False, error=f"Browser error: {exc}")

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        raise NotImplementedError


class WebSearchTool(_BrowserTool):
    """Search the web via DuckDuckGo's HTML endpoint (no API key required)."""

    name = "web.search"
    description = "Search the web and return the top result titles + URLs."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "limit": {"type": "integer", "description": "Max results (default 5)."},
            },
            "required": ["query"],
        }

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 5))
        if not query:
            return ToolCallResult(ok=False, error="Missing 'query'.")

        # DuckDuckGo HTML endpoint: keyless, robust, scrapable.
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)

        from bs4 import BeautifulSoup

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, str]] = []
        for a in soup.select(".result__a")[:limit]:
            title = a.get_text(strip=True)
            href = a.get("href", "")
            results.append({"title": title, "url": str(href or "")})
        return ToolCallResult(
            ok=True, data={"query": query, "results": results, "count": len(results)}
        )


class WebFetchTool(_BrowserTool):
    """Fetch a URL and return its text content."""

    name = "web.fetch"
    description = "Fetch a URL and return the page's text content (HTML stripped)."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch."}},
            "required": ["url"],
        }

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        url = str(args.get("url", "")).strip()
        if not url:
            return ToolCallResult(ok=False, error="Missing 'url'.")
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        from bs4 import BeautifulSoup

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        # Remove scripts/styles before extracting text.
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Truncate to a sane size so it fits in an LLM context.
        max_chars = 8_000
        truncated = text[:max_chars]
        return ToolCallResult(
            ok=True,
            data={
                "url": url,
                "text": truncated,
                "chars": len(text),
                "truncated": len(text) > max_chars,
            },
        )


class WebExtractTool(_BrowserTool):
    """Extract structured data from the current page via a CSS selector."""

    name = "web.extract"
    description = "Extract elements matching a CSS selector from a URL."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to load."},
                "selector": {
                    "type": "string",
                    "description": "CSS selector (default 'a' for all links).",
                },
                "limit": {"type": "integer", "description": "Max matches (default 20)."},
            },
            "required": ["url"],
        }

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        url = str(args.get("url", "")).strip()
        selector = str(args.get("selector", "a"))
        limit = int(args.get("limit", 20))
        if not url:
            return ToolCallResult(ok=False, error="Missing 'url'.")
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        elements = await page.query_selector_all(selector)
        extracted: list[dict[str, str]] = []
        for el in elements[:limit]:
            text = (await el.inner_text()).strip()
            href = await el.get_attribute("href") or ""
            extracted.append({"text": text, "href": href})
        return ToolCallResult(ok=True, data={"url": url, "selector": selector, "items": extracted})


class WebClickTool(_BrowserTool):
    """Click an element on the current page."""

    name = "web.click"
    description = "Click an element matching a CSS selector on a URL."
    risk = RiskLevel.DESTRUCTIVE  # can trigger navigation / form submission

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to load first (optional; uses current page if omitted).",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the element to click.",
                },
            },
            "required": ["selector"],
        }

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        selector = str(args.get("selector", ""))
        url = str(args.get("url", "")).strip()
        if not selector:
            return ToolCallResult(ok=False, error="Missing 'selector'.")
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        el = await page.query_selector(selector)
        if el is None:
            return ToolCallResult(ok=False, error=f"No element matches selector: {selector}")
        await el.click()
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
        return ToolCallResult(ok=True, data={"selector": selector, "url": page.url})


class WebFillFormTool(_BrowserTool):
    """Fill a form field with a value."""

    name = "web.fill_form"
    description = "Fill a form input matching a CSS selector with a value."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to load first (optional)."},
                "selector": {"type": "string", "description": "CSS selector of the input."},
                "value": {"type": "string", "description": "Value to type into the field."},
            },
            "required": ["selector", "value"],
        }

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        selector = str(args.get("selector", ""))
        value = str(args.get("value", ""))
        url = str(args.get("url", "")).strip()
        if not selector:
            return ToolCallResult(ok=False, error="Missing 'selector'.")
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        el = await page.query_selector(selector)
        if el is None:
            return ToolCallResult(ok=False, error=f"No element matches selector: {selector}")
        await el.fill(value)
        return ToolCallResult(ok=True, data={"selector": selector, "value": value, "url": page.url})


class WebScreenshotTool(_BrowserTool):
    """Screenshot the current or a specified page."""

    name = "web.screenshot"
    description = "Take a screenshot of a URL and save it as PNG in the workspace."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to load first (optional)."},
                "path": {"type": "string", "description": "Output PNG path (relative)."},
            },
            "required": ["path"],
        }

    async def _do(self, args: dict[str, Any], ctx: ToolContext, page: Any) -> ToolCallResult:
        from .builtin import _confine

        raw_path = str(args.get("path", "")).strip()
        url = str(args.get("url", "")).strip()
        if not raw_path:
            return ToolCallResult(ok=False, error="Missing 'path'.")
        target = _confine(raw_path, ctx.workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        await page.screenshot(path=str(target), full_page=True)
        return ToolCallResult(
            ok=True, data={"path": raw_path, "url": page.url, "bytes": target.stat().st_size}
        )
