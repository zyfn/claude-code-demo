"""Tool system type definitions.

- Tool: Protocol that any tool must satisfy
- ToolResult: return value from tool execution
- ToolCall: a parsed tool invocation from the LLM response
- tool_to_schema: generates OpenAI-compatible function schema

Hook types (BeforeHook/AfterHook) are gone — replaced by unified HookRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ToolResult:
    output: str
    is_error: bool = False


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, **kwargs: Any) -> ToolResult: ...
    def is_enabled(self) -> bool: ...
    def is_read_only(self) -> bool: ...


@dataclass(slots=True)
class ToolCall:
    """A parsed tool invocation from the LLM response."""
    id: str
    name: str
    params: dict[str, Any]


def tool_to_schema(tool: Tool) -> dict:
    """Generate OpenAI-compatible function tool schema."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, schema in tool.parameters.items():
        param_schema = {k: v for k, v in schema.items() if k != "optional"}
        properties[pname] = param_schema
        if not schema.get("optional", False):
            required.append(pname)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }
