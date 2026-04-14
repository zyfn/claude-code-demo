"""Tool execution utilities — shared by executor.

- AbortSignal: cancellation primitive
- CanUseToolFn: permission function type
- validate_input: parameter validation against tool schema
"""

from __future__ import annotations

from typing import Awaitable, Callable

from src.tools.types import Tool, ToolResult, ToolCall

CanUseToolFn = Callable[[ToolCall], Awaitable[ToolResult | None]]


class AbortSignal:
    """Simple abort signal."""

    def __init__(self):
        self._set = False

    @property
    def is_set(self) -> bool:
        return self._set

    def abort(self) -> None:
        self._set = True


def validate_input(tool: Tool, params: dict) -> str | None:
    """Validate params against tool.parameters. Returns error or None."""
    for pname, schema in tool.parameters.items():
        if not schema.get("optional", False) and pname not in params:
            return f"Missing required parameter: {pname}"

    for pname, value in params.items():
        if pname not in tool.parameters:
            continue
        expected = tool.parameters[pname].get("type")
        if expected and not _check_type(value, expected):
            return f"'{pname}' expected {expected}, got {type(value).__name__}"

    validate_fn = getattr(tool, "validate_input", None)
    if validate_fn:
        return validate_fn(params)

    return None


def _check_type(value, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    elif expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "boolean":
        return isinstance(value, bool)
    elif expected == "array":
        return isinstance(value, list)
    elif expected == "object":
        return isinstance(value, dict)
    return True
