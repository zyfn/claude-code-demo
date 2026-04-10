"""Core ReAct agent loop — pure AsyncGenerator.

Following Claude Code's query.ts architecture:
- QueryParams carries all configuration
- LoopState carries all mutable state across iterations
- State is replaced wholesale at each continue site (whole-state replacement)
- 7 recovery paths via Transition tagged union
- Terminal is YIELDED (not returned) as the final event on exit
- Context compression pipeline runs before each LLM call

No EventBus — events are yielded directly to the caller.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, AsyncGenerator, Union

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

from .state import LoopState, Terminal
from .params import QueryParams
from .deps import QueryDeps
from .transitions import (
    handle_next_turn,
    handle_max_output_tokens_recovery,
    handle_stop_hook_blocking,
)
from src.agent.retry import RetryState, RetryConfig, with_retry, ModelUnavailableError
from src.tools.executor import ToolResult
from src.context.pipeline import ContextPipeline

if TYPE_CHECKING:
    pass


# Union type for what agent_loop yields
AgentEvent = Union[StreamEvent, Terminal]


# ─── AsyncGenerator Loop ───────────────────────────────────────────────────────

async def agent_loop(
    params: QueryParams,
) -> AsyncGenerator[AgentEvent, None]:
    """Core ReAct agent loop as an AsyncGenerator.

    Yields StreamEvent objects during execution.
    Yields Terminal as the final event when the loop exits.

    Architecture (following Claude Code's query loop):
        while True:
            1. Yield TurnStart
            2. Run context compression pipeline (budget → snip → micro → auto)
            3. Check blocking limit
            4. Stream LLM response via with_retry
            5a. No tool calls → recovery paths (max_output_tokens, stop_hook, token_budget)
            5b. Tool calls → execute tools
            6. Continue or yield Terminal

    Args:
        params: QueryParams carrying system_prompt, messages, system_context,
               user_context, max_turns, deps
    """
    deps = params.deps
    if deps is None:
        from .deps import QueryDeps
        deps = QueryDeps(
            call_model=lambda *a, **k: None,  # type: ignore
            count_tokens=lambda *a, **k: 0,    # type: ignore
            get_tool_schemas=lambda: [],
            get_tools=lambda: {},
            execute_tool=lambda *a, **k: ToolResult("error", is_error=True),  # type: ignore
            microcompact=lambda msgs: (msgs, 0),
            autocompact=lambda *a, **k: None,  # type: ignore
        )

    retry_state = RetryState()
    retry_config = deps.retry_config or RetryConfig()
    state = LoopState(messages=list(params.messages))

    # Build context pipeline
    pipeline = _build_pipeline(params, deps)

    # Build system prompt with system context injected
    system_prompt_with_context = _build_system_prompt(
        params.system_prompt,
        params.system_context,
    )

    while state.turn_count < params.max_turns:
        state = state.with_turn(state.turn_count + 1)
        yield TurnStart(turn=state.turn_count)

        # ── Context compression pipeline ───────────────────────────────────

        pipeline_result = await pipeline.run(state.messages, state.auto_compact_tracking)
        state = state.with_messages(pipeline_result.messages)
        if pipeline_result.compaction_result:
            state = state.with_auto_compact_tracking(
                pipeline_result.compaction_result.tracking
            )

        # ── Build messages for API call ───────────────────────────────────

        messages_for_query = _prepend_context(
            system_prompt_with_context,
            pipeline_result.messages,
            params.user_context,
        )

        # ── Blocking limit check ───────────────────────────────────────────

        limit = (deps.resolve_limit or (lambda: 128_000))()
        token_count = deps.count_tokens(messages_for_query, deps.get_tool_schemas())
        if token_count >= limit - 2000:  # 2K buffer
            yield Terminal.blocking_limit(state.turn_count)
            return

        # ── LLM streaming ──────────────────────────────────────────────────

        acc = ChunkAccumulator()
        max_tokens = (
            state.max_output_tokens_override
            or params.max_output_tokens
        )
        try:
            async for chunk in with_retry(
                deps.call_model,
                messages_for_query,
                deps.get_tool_schemas(),
                retry_config,
                retry_state,
                max_tokens,
            ):
                event = handle_chunk(chunk, acc)
                if event is None:
                    continue

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
            yield Terminal.model_error(str(e), state.turn_count)
            return
        except Exception as e:
            yield Terminal.model_error(str(e), state.turn_count)
            return

        # ── No tool calls — recovery paths ────────────────────────────────

        if not acc.tool_calls:
            # max_output_tokens escalation: first hit with no override → escalate and retry
            if state.max_output_tokens_override is None and not acc.text:
                state = state.with_max_output_override(64_000)
                continue  # retry with escalated limit

            # max_output_tokens recovery: already escalated, inject recovery prompt
            if not acc.text:
                state, term = handle_max_output_tokens_recovery(state, acc, deps, [])
                if term:
                    yield term
                    return
                continue

            # Try stop hook (stub)
            state, blocked = handle_stop_hook_blocking(state)
            if blocked:
                continue

            # Normal completion
            yield Terminal.completed(state.turn_count)
            return

        # ── Tool execution ──────────────────────────────────────────────────

        state, tool_events = await _execute_tools(acc.tool_calls, deps, state)
        for ev in tool_events:
            yield ev

        # ── Continue to next turn ─────────────────────────────────────────

        state = handle_next_turn(state)

    yield Terminal.max_turns(state.turn_count)


def _build_pipeline(params: QueryParams, deps: QueryDeps) -> ContextPipeline:
    """Build the context compression pipeline."""
    return ContextPipeline(
        count_tokens=deps.count_tokens,
        resolve_limit=deps.resolve_limit or (lambda: 128_000),
        microcompact_fn=None,  # use default micro_compact
        autocompact_fn=None,  # use default auto_compact
        llm_client=deps.llm_client,
        ratio=0.8,
    )


def _build_system_prompt(
    base_prompt: str,
    system_context: dict[str, str],
) -> str:
    """Build full system prompt with system context appended."""
    if not system_context:
        return base_prompt
    context_lines = "\n".join(f"- {k}: {v}" for k, v in system_context.items())
    return f"{base_prompt}\n\n## System Context\n{context_lines}"


def _prepend_context(
    system_prompt: str,
    messages: list[Message],
    user_context: dict[str, str],
) -> list[Message]:
    """Prepend system prompt and user context to messages.

    Returns a message list suitable for the LLM API call.
    System prompt becomes messages[0]. Each user_context entry is
    prepended as a separate user message.
    """
    result: list[Message] = [Message(role="system", content=system_prompt)]

    # User context as user messages (current_date, claude_md, etc.)
    for key, value in user_context.items():
        if value:
            result.append(Message(role="user", content=f"## {key}\n\n{value}"))

    # Then the actual conversation messages
    result.extend(messages)
    return result


# ─── Tool Execution ────────────────────────────────────────────────────────────

async def _execute_tools(
    tool_calls: list[dict],
    deps: QueryDeps,
    state: LoopState,
) -> tuple[LoopState, list[StreamEvent]]:
    """Execute all tool calls and return (new_state, events)."""
    from src.tools.orchestration import partition_tool_calls, ToolCall

    tools = deps.get_tools()

    # Pre-parse arguments once to avoid duplicate json.loads
    parsed = [
        (tc, json.loads(tc["arguments"]) if tc["arguments"] else {})
        for tc in tool_calls
    ]

    calls = [
        ToolCall(name=tc["name"], params=params, tool_call_id=tc["id"])
        for tc, params in parsed
    ]

    batches = partition_tool_calls(calls, tools)

    results: list[ToolResult] = []
    for batch in batches:
        batch_results = await _execute_batch(batch, deps)
        results.extend(batch_results)

    # Build events and collect new messages from tools
    events: list[StreamEvent] = []
    new_messages: list[Message] = []

    for (tc, params), result in zip(parsed, results):
        events.append(ToolStartEvent(type="tool_start", name=tc["name"], params=params))
        if isinstance(result, Exception):
            result = ToolResult(f"Error: {result}", is_error=True)
        events.append(ToolResultEvent(
            type="tool_result",
            name=tc["name"],
            output=result.output,
            is_error=result.is_error,
        ))
        if result.new_messages:
            new_messages.extend(result.new_messages)

    # Build next state
    next_messages = list(state.messages)
    for tc, result in zip(tool_calls, results):
        next_messages.append(Message(
            role="tool",
            content=result.output,
            tool_call_id=tc["id"],
        ))
    for msg in new_messages:
        next_messages.append(msg)

    return state.with_messages(next_messages), events


async def _execute_batch(batch, deps: QueryDeps) -> list[ToolResult]:
    """Execute a single batch of tool calls."""
    from src.tools.orchestration import ToolCall

    async def exec_fn(name: str, params: dict, tool_call_id: str) -> ToolResult:
        return await deps.execute_tool(name, params, tool_call_id)

    results: list[ToolResult] = []
    if batch.concurrent:
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
        for call in batch.calls:
            result = await exec_fn(call.name, call.params, call.tool_call_id)
            results.append(result)

    return results
