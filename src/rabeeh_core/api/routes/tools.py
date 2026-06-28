"""Tool registry endpoints.

- ``GET /tools``            -> list names + risk classification.
- ``GET /tools/{name}``     -> schema + description for one tool.
- ``GET /tools/schemas``    -> OpenAI-style function-calling bundle.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...tools.registry import get_registry

router = APIRouter()


@router.get("")
async def list_tools() -> dict[str, object]:
    """List every registered tool with its static metadata."""
    reg = get_registry()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "risk": t.risk.value,
            }
            for t in reg.all()
        ]
    }


@router.get("/schemas")
async def tool_schemas() -> dict[str, list[dict[str, object]]]:
    """Return the OpenAI ``tools`` payload for all registered tools."""
    return {"tools": get_registry().function_schemas()}


@router.get("/{name}")
async def tool_detail(name: str) -> dict[str, object]:
    """Return the full descriptor for a single tool."""
    tool = get_registry().get(name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {name}")
    return {
        "name": tool.name,
        "description": tool.description,
        "risk": tool.risk.value,
        "schema": tool.schema(),
        "function": tool.as_function_tool(),
    }
