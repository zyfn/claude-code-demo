"""Core ReAct agent loop — pure AsyncGenerator.

Following Claude Code's query.ts:
- QueryParams carries all configuration
- LoopState carries all mutable state (whole-state replacement)
- 7 recovery paths via Transition tagged union
- Terminal is YIELDED as the final event
- Context compression pipeline runs before each LLM call

No EventBus — events go directly to the caller.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, AsyncGenerator, Union

from litellm.types.utils import Message

from .types import (
    StreamEvent, TurnStart, TextEvent, ToolStartEvent,
    ToolResultEvent, StreamEnd, FinalEvent, ErrorEvent,
    ChunkAccumulator, handle_chunk,
)
from .state import LoopState, Terminal
from .params import QueryParams
from .deps import QueryDeps
from .transitions import (
    handle_next_turn,
    handle_max_output_tokens_recovery,
    handle_stop_hook_blocking,
)
from .retry import RetryState, RetryConfig, with_retry, ModelUnavailableError
from src.tools.executor import ToolResult
from src.tools.orchestration import StreamingToolExecutor, ToolUse
from src.context.pipeline import ContextPipeline

if TYPE_CHECKING:
    pass


AgentEvent = Union[StreamEvent, Terminal]


async def agent_loop(
    params: QueryParams,
) -> AsyncGenerator[AgentEvent, None]:
    """ReAct loop: yield events, never return directly.

    Flow per turn:
        1. Yield TurnStart
        2. Run context compression pipeline
        3. Check blocking limit
        4. Stream LLM response
        5a. No tool calls → recovery paths → continue or Terminal
        5b. Tool calls → execute → continue or Terminal
    """
    deps = params.deps
    if deps is None:
        deps = _default_deps()

    retry_state = RetryState()
    retry_config = deps.retry_config or RetryConfig()
    state = LoopState(messages=list(params.messages))
    pipeline = _build_pipeline(params, deps)
    system_prompt = _inject_context(params.system_prompt, params.system_context)

    while state.turn_count < params.max_turns:
        state = state.with_turn(state.turn_count + 1)
        yield TurnStart(turn=state.turn_count)

        # ── Context compression pipeline ───────────────────────────────────
        result = await pipeline.run(state.messages, state.auto_compact_tracking)
        state = state.with_messages(result.messages)
        if result.compaction_result:
            state = state.with_auto_compact_tracking(result.compaction_result.tracking)

        # ── Build API call messages ───────────────────────────────────────
        messages_for_query = _prepend_context(system_prompt, result.messages, params.user_context)

        # ── Blocking limit check ───────────────────────────────────────────
        limit = (deps.resolve_limit or (lambda: 128_000))()
        if deps.count_tokens(messages_for_query, deps.get_tool_schemas()) >= limit - 2000:
            yield Terminal.blocking_limit(state.turn_count)
            return

        # ── LLM streaming ──────────────────────────────────────────────────
        acc = ChunkAccumulator()
        max_tokens = state.max_output_tokens_override or params.max_output_tokens

        try:
            async for chunk in with_retry(
                deps.call_model, messages_for_query,
                deps.get_tool_schemas(), retry_config, retry_state, max_tokens,
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

        # ── No tool calls — recovery paths ─────────────────────────────────
        if not acc.tool_calls:
            if state.max_output_tokens_override is None and not acc.text:
                state = state.with_max_output_override(64_000)
                continue
            if not acc.text:
                state, term = handle_max_output_tokens_recovery(state, acc, deps, [])
                if term:
                    yield term
                    return
                continue
            state, blocked = handle_stop_hook_blocking(state)
            if blocked:
                continue
            next_msgs = list(state.messages) + [Message(role="assistant", content=acc.text)]
            state = state.with_messages(next_msgs)
            yield Terminal.completed(state.turn_count, acc.text)
            return

        # ── Tool execution ───────────────────────────────────────────────
        executor = StreamingToolExecutor(
            tools=deps.get_tools(),
            execute_tool_fn=deps.execute_tool,
        )
        for tc in acc.tool_calls:
            try:
                tool_params = json.loads(tc["arguments"]) if tc.get("arguments") else {}
            except json.JSONDecodeError:
                tool_params = {}
            executor.add_tool_use(ToolUse(
                name=tc["name"],
                params=tool_params,
                tool_call_id=tc["id"],
            ))

        completed = await executor.drain()

        next_msgs = list(state.messages)
        for tc in acc.tool_calls:
            next_msgs.append(Message(role="assistant", content="", tool_call_id=tc["id"]))
        for (tu, result) in completed:
            yield ToolResultEvent(type="tool_result", name=tu.name, output=result.output, is_error=result.is_error)
            next_msgs.append(Message(role="tool", content=result.output, tool_call_id=tu.tool_call_id))

        state = state.with_messages(next_msgs)
        state = handle_next_turn(state)

    yield Terminal.max_turns(state.turn_count)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _default_deps() -> QueryDeps:
    """Fallback deps for testing without a real agent."""
    return QueryDeps(
        call_model=lambda *a, **k: None,  # type: ignore
        count_tokens=lambda *a, **k: 0,    # type: ignore
        get_tool_schemas=lambda: [],
        get_tools=lambda: {},
        execute_tool=lambda *a, **k: ToolResult("error", is_error=True),  # type: ignore
        microcompact=lambda msgs: (msgs, 0),
        autocompact=lambda *a, **k: None,  # type: ignore
    )


def _build_pipeline(params: QueryParams, deps: QueryDeps) -> ContextPipeline:
    """Build compression pipeline using params.context_ratio."""
    return ContextPipeline(
        count_tokens=deps.count_tokens,
        resolve_limit=deps.resolve_limit or (lambda: 128_000),
        llm_client=deps.llm_client,
        ratio=params.context_ratio,
    )


def _inject_context(base_prompt: str, system_context: dict[str, str]) -> str:
    """Append system context key-value pairs to system prompt."""
    if not system_context:
        return base_prompt
    lines = "\n".join(f"- {k}: {v}" for k, v in system_context.items())
    return f"{base_prompt}\n\n## System Context\n{lines}"


def _prepend_context(
    system_prompt: str,
    messages: list[Message],
    user_context: dict[str, str],
) -> list[Message]:
    """Build API call message list: system + user_context entries + conversation."""
    result: list[Message] = [Message(role="system", content=system_prompt)]
    for key, value in user_context.items():
        if value:
            result.append(Message(role="user", content=f"## {key}\n\n{value}"))
    result.extend(messages)
    return result
