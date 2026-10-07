"""Canonical tool execution with PeoplePay authority.

A model calling ``purchase()`` authorizes NOTHING. Tools are registered with an
authority level; consequential tools are never executed from the model loop -- they
return a pending-approval marker that PeoplePay's Gateway/approval policy must resolve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .canonical import ToolCallPart, ToolDefinition, ToolResultPart


@dataclass
class RegisteredTool:
    definition: ToolDefinition
    handler: Callable[[dict[str, Any]], str]
    consequential: bool = False       # money, orders, submissions, operational changes


class ToolRegistry:
    def __init__(self) -> None:
        self._t: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, handler: Callable[[dict], str], *, consequential: bool = False) -> None:
        self._t[definition.name] = RegisteredTool(definition, handler, consequential)

    def definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._t.values()]

    def execute(self, call: ToolCallPart) -> tuple[ToolResultPart, dict | None]:
        t = self._t.get(call.name)
        if t is None:
            return ToolResultPart(call.call_id, f"unknown tool {call.name!r}", True), None
        if t.consequential:
            pending = {"tool": call.name, "arguments": call.arguments, "call_id": call.call_id,
                       "requires": "human approval through the PeoplePay Gateway"}
            return ToolResultPart(call.call_id, "Not executed: this action requires explicit human approval "
                                  "through PeoplePay. The request has been recorded as pending.", True), pending
        try:
            return ToolResultPart(call.call_id, str(t.handler(call.arguments))), None
        except Exception as exc:   # tool failure must not crash the loop or leak internals
            return ToolResultPart(call.call_id, f"tool failed: {type(exc).__name__}", True), None
