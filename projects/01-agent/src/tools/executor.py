"""Tool executor with middleware hooks.

Hooks run before/after every tool execution, enabling logging,
metrics, rate limiting, retry, and other cross-cutting concerns
without polluting tool implementation code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, TYPE_CHECKING

from src.tools.base import BaseTool

if TYPE_CHECKING:
    from litellm.types.utils import Message


@dataclass
class ToolResult:
    """Result from a tool execution.

    Attributes:
        output: the text/structured data to return to the model.
        is_error: whether this is an error result.
        new_messages: optional messages to inject into conversation (used by SkillTool).
    """
    output: str
    is_error: bool = False
    new_messages: Optional[list["Message"]] = None


@dataclass
class ToolHookContext:
    """Context passed to every hook call."""
    tool_name: str
    params: dict
    tool_call_id: str


# Hooks: sync or async, return None to continue, return ToolResult to short-circuit
BeforeHook = Callable[[ToolHookContext], Awaitable[ToolResult | None] | ToolResult | None]
AfterHook = Callable[[ToolHookContext, ToolResult], Awaitable[None] | None]


class ToolExecutor:
    """Executes tools with before/after hooks in a pipeline."""

    def __init__(self, tools: list[BaseTool]):
        self._tools = {t.name: t for t in tools}
        self._before_hooks: list[BeforeHook] = []
        self._after_hooks: list[AfterHook] = []

    def add_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def remove_tool(self, name: str) -> None:
        self._tools.pop(name, None)

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def before(self, hook: BeforeHook) -> None:
        """Register a before-execution hook. Runs in registration order."""
        self._before_hooks.append(hook)

    def after(self, hook: AfterHook) -> None:
        """Register an after-execution hook. Runs in registration order."""
        self._after_hooks.append(hook)

    async def execute(self, name: str, params: dict, tool_call_id: str) -> ToolResult:
        ctx = ToolHookContext(tool_name=name, params=params, tool_call_id=tool_call_id)

        # Run before hooks
        for hook in self._before_hooks:
            result = hook(ctx)
            if hasattr(result, "__await__"):
                result = await result
            if result is not None:
                return result

        # Execute tool
        tool = self._tools.get(name)
        if not tool:
            result = ToolResult(f"Unknown tool: {name}", is_error=True)
        else:
            result = await tool.execute(**params)

        # Run after hooks
        for hook in self._after_hooks:
            hook_result = hook(ctx, result)
            if hasattr(hook_result, "__await__"):
                await hook_result

        return result

    @property
    def tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_schemas(self) -> list[dict]:
        return [t.to_schema() for t in self._tools.values()]
