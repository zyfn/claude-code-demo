"""Tool executor — permission + concurrent execution + event lifecycle.

Single responsibility: take parsed ToolCalls, produce ToolEvents + tool messages.

Two phases:
  Phase 1 (submit, sequential):
    validate → hooks → permission for each call.
    Yields ToolEvent(rejected) or ToolEvent(running).
    Does NOT start execution — only records approved calls.

  Phase 2 (drain, concurrent):
    Starts all approved tasks, then yields ToolEvent(completed/error)
    as each finishes. This separation ensures the UI can render ⏳
    before any tool completes.

query.py just forwards events and collects messages — no manual event construction.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator, TYPE_CHECKING

from src.tools.types import Tool, ToolResult, ToolCall
from src.tools.execution import validate_input, CanUseToolFn, AbortSignal
from src.types import ToolEvent
from src.constants import MAX_CONCURRENT_TOOLS
from src.hooks import HookEvent

if TYPE_CHECKING:
    from src.hooks import HookRegistry


@dataclass
class _Entry:
    call: ToolCall
    tool: Tool | None = None       # None for rejected entries
    rejected: bool = False
    result: ToolResult | None = None
    task: asyncio.Task[ToolResult] | None = None


class ToolExecutor:
    def __init__(
        self,
        tools: dict[str, Tool],
        hooks: "HookRegistry | None" = None,
        can_use_tool: CanUseToolFn | None = None,
        abort_signal: AbortSignal | None = None,
        max_concurrent: int = MAX_CONCURRENT_TOOLS,
    ):
        self._tools = tools
        self._hooks = hooks
        self._can_use_tool = can_use_tool
        self._abort_signal = abort_signal
        self._sem = asyncio.Semaphore(max_concurrent)
        self._entries: list[_Entry] = []

    async def submit(self, calls: list[ToolCall]) -> AsyncGenerator[ToolEvent, None]:
        """Phase 1: validate → hooks → permission for each call.

        Yields ToolEvent(rejected) or ToolEvent(running) for each call.
        Does NOT start execution — approved calls are recorded for drain().
        """
        self._entries.clear()

        for call in calls:
            tool = self._tools.get(call.name)

            # Unknown tool
            if not tool:
                r = ToolResult(f"Unknown tool: {call.name}", is_error=True)
                self._entries.append(_Entry(call=call, rejected=True, result=r))
                yield _event(call, "rejected", r.output)
                continue

            # Input validation
            error = validate_input(tool, call.params)
            if error:
                r = ToolResult(f"InputValidationError: {error}", is_error=True)
                self._entries.append(_Entry(call=call, rejected=True, result=r))
                yield _event(call, "rejected", r.output)
                continue

            # PreToolUse hooks
            if self._hooks:
                blocked = False
                for hr in await self._hooks.dispatch(HookEvent.PRE_TOOL_USE, {"call": call}):
                    if isinstance(hr, ToolResult):
                        self._entries.append(_Entry(call=call, rejected=True, result=hr))
                        yield _event(call, "rejected", hr.output)
                        blocked = True
                        break
                if blocked:
                    continue

            # Permission check (only for non-read-only tools)
            if self._can_use_tool and not tool.is_read_only():
                result = await self._can_use_tool(call)
                if result is not None:
                    self._entries.append(_Entry(call=call, rejected=True, result=result))
                    yield _event(call, "rejected", result.output)
                    continue

            # Approved — record for drain(), do NOT start yet
            self._entries.append(_Entry(call=call, tool=tool))
            yield _event(call, "running")

    async def drain(self) -> AsyncGenerator[tuple[ToolEvent, ToolResult], None]:
        """Phase 2: start all approved tasks, yield results as each completes.

        Tasks are created HERE (not in submit) so the UI has time to
        render ⏳ before any tool starts executing.
        """
        # Start all approved tasks now
        pending: dict[asyncio.Task, _Entry] = {}
        for entry in self._entries:
            if not entry.rejected and entry.tool is not None:
                task = asyncio.create_task(self._run(entry))
                entry.task = task
                pending[task] = entry

        # Yield results as they complete
        remaining = set(pending.keys())
        while remaining:
            done, remaining = await asyncio.wait(remaining, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                entry = pending[task]
                try:
                    result = task.result()
                except Exception as e:
                    result = ToolResult(f"Task error: {e}", is_error=True)
                entry.result = result
                status = "error" if result.is_error else "completed"
                yield (_event(entry.call, status, result.output), result)

    def collect_tool_messages(self) -> list:
        """Collect all tool messages (rejected + completed) for the conversation.

        Call after drain() completes. Returns litellm Message objects.
        """
        from litellm.types.utils import Message

        msgs: list[Message] = []
        for entry in self._entries:
            if entry.result is not None:
                msgs.append(Message(role="tool", content=entry.result.output, tool_call_id=entry.call.id))
        self._entries.clear()
        return msgs

    async def _run(self, entry: _Entry) -> ToolResult:
        assert entry.tool is not None
        async with self._sem:
            if self._abort_signal and self._abort_signal.is_set:
                return ToolResult("Aborted", is_error=True)
            try:
                result = await entry.tool.execute(**entry.call.params)
            except Exception as e:
                result = ToolResult(f"Tool error: {e}", is_error=True)
            if self._hooks:
                await self._hooks.dispatch(HookEvent.POST_TOOL_USE, {"call": entry.call, "result": result})
            return result

    @property
    def approved_count(self) -> int:
        """Number of approved (non-rejected) tools after submit."""
        return sum(1 for e in self._entries if not e.rejected)

    @property
    def tools(self) -> dict[str, Tool]:
        return self._tools

    @property
    def tool_schemas(self) -> list[dict]:
        from src.tools.types import tool_to_schema
        return [tool_to_schema(t) for t in self._tools.values()]


def _event(call: ToolCall, status: str, output: str = "") -> ToolEvent:
    return ToolEvent(
        name=call.name, params=call.params,
        tool_call_id=call.id, status=status, output=output,
    )
