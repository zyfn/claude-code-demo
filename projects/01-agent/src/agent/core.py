"""Core ReAct agent loop — pure AsyncGenerator.

This module contains only the loop logic. All external dependencies
(LLM client, tool executor, context manager) are passed via AgentDeps.

Architecture (following Claude Code's query loop):
    while True:
        1. context = prepare_context(messages)
        2. response = yield* call_model_with_retry(context)
        3. if no tool_use: yield final; break
        4. results = yield* execute_tools_streaming(tool_uses)
        5. messages.append(response, results)

No EventBus — events are yielded directly to the caller.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncGenerator

from litellm.types.utils import Message

from src.agent.types import (
    StreamEvent,
    TurnStart,
    TextEvent,
    ToolStartEvent,
    ToolResultEvent,
    StreamEnd,
    FinalEvent,
    ErrorEvent,
    ChunkAccumulator,
    handle_chunk,
)
from src.agent.deps import AgentDeps
from src.agent.retry import RetryState, RetryConfig, with_retry, ModelUnavailableError
from src.tools.executor import ToolResult

if TYPE_CHECKING:
    pass


# ─── Config ────────────────────────────────────────────────────────────────────

@dataclass
class LoopConfig:
    """Configuration for a single agent loop run."""
    name: str = "agent"
    max_iterations: int = 20
    max_tokens: int = 8192


# ─── AsyncGenerator Loop ───────────────────────────────────────────────────────

async def agent_loop(
    config: LoopConfig,
    deps: AgentDeps,
    messages: list[Message],
) -> AsyncGenerator[StreamEvent, None]:
    """Core ReAct agent loop as an AsyncGenerator.

    Yields StreamEvent objects directly to the caller. No EventBus.

    Usage:
        deps = AgentDeps(
            call_model=client.chat,
            count_tokens=client.count_tokens,
            ...
        )
        async for event in agent_loop(config, deps, messages):
            if isinstance(event, TextEvent):
                print(event.text, end="", flush=True)

    Args:
        config: Loop configuration (name, max_iterations, etc.)
        deps: All external dependencies
        messages: Conversation history (modified in-place)
    """
    state = RetryState()
    retry_config = deps.retry_config or RetryConfig()
    turn_count = 0

    while turn_count < config.max_iterations:
        turn_count += 1
        yield TurnStart(turn=turn_count)

        # ── LLM streaming ──────────────────────────────────────────────────

        acc = ChunkAccumulator()

        try:
            async for chunk in with_retry(
                deps.call_model,
                messages,
                deps.get_tool_schemas(),
                retry_config,
                state,
                config.max_tokens,
            ):
                event = handle_chunk(chunk, acc)
                if event is None:
                    continue

                # Update accumulator for final assembly
                if isinstance(event, TextEvent):
                    if event.type == "content":
                        acc.text += event.text
                    yield event
                elif isinstance(event, StreamEnd):
                    acc.text = event.accumulated_text or acc.text
                    acc.tool_calls = event.accumulated_tool_calls or acc.tool_calls
                    acc.usage = event.usage
                    yield event
                else:
                    yield event

        except ModelUnavailableError as e:
            yield ErrorEvent(message=str(e), reason="model_unavailable")
            return
        except Exception as e:
            yield ErrorEvent(message=f"Error: {e}", reason="error")
            return

        # ── No tool calls → final response ─────────────────────────────────

        if not acc.tool_calls:
            yield FinalEvent(text=acc.text, reason="completed")
            return

        # ── Execute tools ──────────────────────────────────────────────────

        tool_events = await _execute_tools(
            acc.tool_calls,
            deps,
            messages,
        )
        for ev in tool_events:
            yield ev

        # ── Context compaction at turn end ─────────────────────────────────

        deps.apply_context_compactions(deps.get_tool_schemas(), deps.llm_client)

    # Max iterations reached
    yield FinalEvent(text=acc.text, reason="max_turns")


# ─── Tool Execution ────────────────────────────────────────────────────────────

async def _execute_tools(
    tool_calls: list[dict],
    deps: AgentDeps,
    messages: list[Message],
) -> list[StreamEvent]:
    """Execute all tool calls and return events.

    Runs tools in batches based on concurrency safety (from orchestration.py).
    """
    from src.tools.orchestration import partition_tool_calls, ToolCall

    # Get tool instances for partition
    tools = deps.get_tools()

    # Pre-parse arguments once to avoid duplicate json.loads
    parsed = [
        (tc, json.loads(tc["arguments"]) if tc["arguments"] else {})
        for tc in tool_calls
    ]

    # Convert to ToolCall format
    calls = [
        ToolCall(name=tc["name"], params=params, tool_call_id=tc["id"])
        for tc, params in parsed
    ]

    # Partition into batches
    batches = partition_tool_calls(calls, tools)

    results: list[ToolResult] = []
    for batch in batches:
        # Execute batch
        batch_results = await _execute_batch(batch, deps)
        results.extend(batch_results)

    # Generate events
    events: list[StreamEvent] = []
    new_messages: list[Message] = []

    for (tc, params), result in zip(parsed, results):
        # Emit ToolStartEvent before ToolResultEvent
        events.append(ToolStartEvent(
            type="tool_start",
            name=tc["name"],
            params=params,
        ))
        if isinstance(result, Exception):
            result = ToolResult(f"Error: {result}", is_error=True)
        events.append(ToolResultEvent(
            type="tool_result",
            name=tc["name"],
            output=result.output,
            is_error=result.is_error,
        ))
        # Collect new messages from tool results (generic, tool-agnostic)
        if result.new_messages:
            new_messages.extend(result.new_messages)

    # Append tool results to messages
    _append_tool_results(messages, tool_calls, results)

    # Inject new messages from skills
    for msg in new_messages:
        messages.append(msg)

    return events


async def _execute_batch(batch, deps: AgentDeps) -> list[ToolResult]:
    """Execute a single batch of tool calls."""
    from src.tools.orchestration import ToolCall

    async def exec_fn(name: str, params: dict, tool_call_id: str) -> ToolResult:
        return await deps.execute_tool(name, params, tool_call_id)

    results: list[ToolResult] = []
    if batch.concurrent:
        # Concurrent batch — run all at once (up to MAX_CONCURRENT)
        import asyncio
        chunk_size = 10
        for i in range(0, len(batch.calls), chunk_size):
            chunk = batch.calls[i:i + chunk_size]
            chunk_results = await asyncio.gather(
                *[exec_fn(c.name, c.params, c.tool_call_id) for c in chunk],
                return_exceptions=True,
            )
            for r in chunk_results:
                if isinstance(r, Exception):
                    results.append(ToolResult(f"Error: {r}", is_error=True))
                else:
                    results.append(r)
    else:
        # Serial batch
        for call in batch.calls:
            result = await exec_fn(call.name, call.params, call.tool_call_id)
            results.append(result)

    return results


def _append_tool_results(
    messages: list[Message],
    tool_calls: list[dict],
    results: list[ToolResult],
) -> None:
    """Append tool result messages to the conversation history.

    Each tool result is a separate Message with role='tool'.
    """
    for tc, result in zip(tool_calls, results):
        messages.append(Message(
            role="tool",
            content=result.output,
            tool_call_id=tc["id"],
        ))
