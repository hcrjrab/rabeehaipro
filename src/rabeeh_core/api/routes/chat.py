"""WebSocket-based streaming chat endpoint.

Allows the frontend / Electron app to send messages and receive token-by-token
streaming responses from the configured LLM provider (via the router).

Endpoints
---------
- ``WS /chat/stream`` — Full-duplex streaming chat.
- ``POST /chat/completion`` — Non-streaming completion (legacy / HTTP-only).

Protocol (WebSocket)
--------------------
Client → Server::
    {"messages": [{"role": "user", "content": "..."}], "stream": true}
    {"tool_results": [{"tool_name": "...", "result": {...}}]}

Server → Client::
    {"kind": "chunk", "content": "partial text"}
    {"kind": "tool_call", "tool_calls": [...]}
    {"kind": "done", "content": "...", "usage": {...}, "finish_reason": "stop"}
    {"kind": "error", "error": "..."}
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ...config.settings import get_settings
from ...llm.base import LLMMessage
from ...llm.registry import get_client
from ...llm.router import build_router

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# HTTP completion endpoint (non-streaming)
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(
        ..., description='Messages array: [{"role": "...", "content": "..."}]'
    )
    temperature: float = 0.2
    max_tokens: int | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    model: str = ""
    provider: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: str = "stop"


@router.post("/completion")
async def chat_completion(body: ChatRequest) -> ChatResponse:
    """Non-streaming completion. Useful for simple tool calls and tests."""
    settings = get_settings()
    messages = [
        LLMMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in body.messages
    ]

    if settings.default_provider in ("mock", "ollama", "openrouter", "litellm"):
        client = get_client()
    else:
        client = get_client()

    response = await client.chat(
        messages,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )

    return ChatResponse(
        content=response.content,
        model=response.model,
        provider=response.provider,
        usage={
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        finish_reason=response.finish_reason,
    )


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------


@router.websocket("/stream")
async def chat_stream_ws(websocket: WebSocket) -> None:
    """Full-duplex WebSocket for streaming chat.

    Accepts one JSON message per exchange, streams tokens back, then waits
    for the next user message (multi-turn).
    """
    await websocket.accept()
    _log.info("WebSocket /chat/stream connected")

    settings = get_settings()
    if hasattr(settings, "streaming_enabled") and not settings.streaming_enabled:
        await websocket.send_json(
            {"kind": "error", "error": "Streaming is disabled by configuration."}
        )
        await websocket.close()
        return

    router = build_router()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"kind": "error", "error": "Invalid JSON."})
                continue

            messages_raw = data.get("messages", [])
            temperature = data.get("temperature", 0.2)
            max_tokens = data.get("max_tokens")
            tools = data.get("tools")
            model_hint = data.get("model")

            messages = [
                LLMMessage(role=m.get("role", "user"), content=m.get("content", ""))
                for m in messages_raw
            ]

            kwargs: dict[str, Any] = {}
            if model_hint:
                kwargs["model"] = model_hint

            try:
                async for event in router.chat_stream(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                ):
                    payload: dict[str, Any] = {"kind": event.kind}

                    if event.kind == "chunk":
                        payload["content"] = event.content
                    elif event.kind == "tool_call":
                        payload["tool_calls"] = event.tool_calls or []
                    elif event.kind == "done":
                        payload["content"] = event.content
                        payload["usage"] = (
                            {
                                "prompt_tokens": event.usage.prompt_tokens if event.usage else 0,
                                "completion_tokens": event.usage.completion_tokens
                                if event.usage
                                else 0,
                                "total_tokens": event.usage.total_tokens if event.usage else 0,
                            }
                            if event.usage
                            else {}
                        )
                        payload["model"] = event.model
                        payload["provider"] = event.provider
                        payload["finish_reason"] = event.finish_reason
                    elif event.kind == "error":
                        payload["error"] = event.error or "Unknown streaming error"

                    await websocket.send_json(payload)

                    if event.kind in ("done", "error"):
                        break

            except Exception as exc:
                _log.exception("Streaming error")
                await websocket.send_json({"kind": "error", "error": str(exc)})

    except WebSocketDisconnect:
        _log.info("WebSocket /chat/stream disconnected")
    except Exception:
        _log.exception("WebSocket error")
    finally:
        with contextlib.suppress(Exception):
            await router.close()
