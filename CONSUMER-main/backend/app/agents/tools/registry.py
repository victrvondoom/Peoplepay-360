"""Tool Execution framework — a small registry agents can call into for
non-LLM capabilities (lookups, calculation, parsing) instead of only ever
generating text. Each tool declares a name/description/handler; call() runs
it and returns a uniform result envelope so a calling agent doesn't need to
know each tool's internal error handling.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolHandler = Callable[..., Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, handler: ToolHandler) -> None:
        self._tools[name] = Tool(name=name, description=description, handler=handler)

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    async def call(self, name: str, **kwargs) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"tool": name, "ok": False, "error": f"Unknown tool: {name}", "available": list(self._tools)}
        start = time.monotonic()
        try:
            result = await tool.handler(**kwargs)
            return {
                "tool": name,
                "ok": True,
                "result": result,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
            }
        except Exception as exc:
            return {
                "tool": name,
                "ok": False,
                "error": str(exc),
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
            }


tool_registry = ToolRegistry()
