"""Tool orchestration — StreamingToolExecutor.

StreamingToolExecutor executes tools as their tool_use blocks arrive
in the LLM stream, without waiting for the stream to complete.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.tools.base import BaseTool
from src.tools.executor import ToolResult


MAX_CONCURRENT = 10


# ─── Streaming Tool Executor ───────────────────────────────────────────────────

@dataclass
class ToolUse:
    """A complete tool use (all arguments received)."""
    name: str
    params: dict
    tool_call_id: str


class StreamingToolExecutor:
    """Executes tools as they arrive in the LLM stream.

    While the LLM streams tool_use blocks, this executor:
    1. Collects tool_use blocks as they complete (arguments fully received)
    2. Submits them for execution immediately
    3. Yields ToolResultEvents as each tool completes
    4. Allows the LLM stream to continue uninterrupted

    This is the key architectural difference from batch execution:
    tools run in parallel with the LLM stream rather than waiting for it to end.
    """

    def __init__(
        self,
        tools: dict[str, BaseTool],
        execute_tool_fn: callable,
        max_concurrent: int = MAX_CONCURRENT,
    ):
        self._tools = tools
        self._execute_fn = execute_tool_fn
        self._max_concurrent = max_concurrent

        # Pending tool uses waiting to be assigned a worker
        self._pending: list[ToolUse] = []
        # Currently running tasks: tool_call_id → asyncio.Task
        self._running: dict[str, asyncio.Task] = {}
        # Completed results not yet yielded
        self._completed: list[tuple[ToolUse, ToolResult]] = []

        self._executor_lock = asyncio.Lock()

    def add_tool_use(self, tool_use: ToolUse) -> None:
        """Add a complete tool use to the pending queue and try to execute it."""
        self._pending.append(tool_use)
        asyncio.create_task(self._try_dispatch())

    async def _try_dispatch(self) -> None:
        """Try to dispatch pending tools up to max_concurrent."""
        async with self._executor_lock:
            while self._pending and len(self._running) < self._max_concurrent:
                tu = self._pending.pop(0)
                self._running[tu.tool_call_id] = asyncio.create_task(
                    self._execute(tu)
                )

    async def _execute(self, tool_use: ToolUse) -> None:
        """Execute a single tool and store its result."""
        try:
            result = await self._execute_fn(
                tool_use.name,
                tool_use.params,
                tool_use.tool_call_id,
            )
        except Exception as e:
            result = ToolResult(f"Error: {e}", is_error=True)

        async with self._executor_lock:
            if tool_use.tool_call_id in self._running:
                del self._running[tool_use.tool_call_id]
            self._completed.append((tool_use, result))

    async def drain(self) -> list[tuple[ToolUse, ToolResult]]:
        """Wait for all running tools to complete and return results.

        Also re-dispatches any pending tools that couldn't be dispatched earlier
        (because _running was full when they were added).
        """
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
        # Re-dispatch any pending items that were stranded when _running was full
        await self._try_dispatch()
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
        return self._completed

    def drain_completed(self) -> list[tuple[ToolUse, ToolResult]]:
        """Return and clear completed results without waiting."""
        completed = list(self._completed)
        self._completed.clear()
        return completed
