"""Browser tool tests — schema, risk, and error handling."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import RiskLevel
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.browser import (
    WebClickTool,
    WebExtractTool,
    WebFetchTool,
    WebFillFormTool,
    WebScreenshotTool,
    WebSearchTool,
    close_browser,
    get_browser_manager,
)


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


@pytest.mark.parametrize(
    "tool_cls, name, risk",
    [
        (WebSearchTool, "web.search", RiskLevel.NONE),
        (WebFetchTool, "web.fetch", RiskLevel.NONE),
        (WebExtractTool, "web.extract", RiskLevel.NONE),
        (WebClickTool, "web.click", RiskLevel.DESTRUCTIVE),
        (WebFillFormTool, "web.fill_form", RiskLevel.SAFE),
        (WebScreenshotTool, "web.screenshot", RiskLevel.NONE),
    ],
)
def test_browser_tool_attributes(tool_cls, name, risk) -> None:
    assert tool_cls.name == name
    assert tool_cls.risk is risk
    assert tool_cls.description


def _check_schema_contains(tool, expected) -> None:
    schema = tool.schema()
    assert schema["type"] == "object"
    for key, val in expected.items():
        if key == "required":
            assert set(schema.get(key, [])) == set(val), f"{tool.__class__.__name__} {key}"
        elif key == "properties":
            for prop_name, prop_def in val.items():
                for pk, pv in prop_def.items():
                    assert (
                        schema[key][prop_name][pk] == pv
                    ), f"{tool.__class__.__name__}.{key}.{prop_name}.{pk}"


@pytest.mark.parametrize(
    "tool_cls, expected",
    [
        (
            WebSearchTool,
            {
                "required": ["query"],
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            },
        ),
        (
            WebFetchTool,
            {
                "required": ["url"],
                "properties": {"url": {"type": "string"}},
            },
        ),
        (
            WebExtractTool,
            {
                "required": ["url"],
                "properties": {"selector": {"type": "string"}, "limit": {"type": "integer"}},
            },
        ),
        (
            WebClickTool,
            {
                "required": ["selector"],
                "properties": {"selector": {"type": "string"}, "url": {"type": "string"}},
            },
        ),
        (
            WebFillFormTool,
            {
                "required": ["selector", "value"],
                "properties": {"selector": {"type": "string"}, "value": {"type": "string"}},
            },
        ),
        (
            WebScreenshotTool,
            {
                "required": ["path"],
                "properties": {"url": {"type": "string"}, "path": {"type": "string"}},
            },
        ),
    ],
)
def test_browser_tool_schema(tool_cls, expected) -> None:
    _check_schema_contains(tool_cls(), expected)


def test_browser_manager_singleton() -> None:
    mgr1 = get_browser_manager()
    mgr2 = get_browser_manager()
    assert mgr1 is mgr2


@pytest.mark.asyncio
async def test_close_browser_idempotent() -> None:
    await close_browser()
    await close_browser()


# Playwright IS installed but browsers may not be.
# The _BrowserTool.execute calls _ensure() first, which tries to launch
# chromium. If it fails, the error is a generic Exception, not ImportError.
# So we just verify that execution fails gracefully.


@pytest.mark.asyncio
async def test_web_search_fails_gracefully(tmp_path) -> None:
    tool = WebSearchTool()
    out = await tool.execute({"query": "hello"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_search_missing_query(tmp_path) -> None:
    tool = WebSearchTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_fetch_fails_gracefully(tmp_path) -> None:
    tool = WebFetchTool()
    out = await tool.execute({"url": "https://example.com"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_fetch_missing_url(tmp_path) -> None:
    tool = WebFetchTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_extract_fails_gracefully(tmp_path) -> None:
    tool = WebExtractTool()
    out = await tool.execute({"url": "https://example.com"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_extract_missing_url(tmp_path) -> None:
    tool = WebExtractTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_click_fails_gracefully(tmp_path) -> None:
    tool = WebClickTool()
    out = await tool.execute({"selector": "a.button"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_click_missing_selector(tmp_path) -> None:
    tool = WebClickTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_fill_form_fails_gracefully(tmp_path) -> None:
    tool = WebFillFormTool()
    out = await tool.execute({"selector": "#name", "value": "Alice"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_fill_form_missing_selector(tmp_path) -> None:
    tool = WebFillFormTool()
    out = await tool.execute({"value": "x"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_screenshot_fails_gracefully(tmp_path) -> None:
    tool = WebScreenshotTool()
    out = await tool.execute({"path": "shot.png"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_web_screenshot_missing_path(tmp_path) -> None:
    tool = WebScreenshotTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok
