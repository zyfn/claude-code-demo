"""Core agent loop — pure loop logic.

Context injection (Claude Code semantics):
- system_context → appended to system prompt → system message (built once)
- user_context → prepended as user messages EACH API call (not in history)
  This ensures CLAUDE.md/date survive compaction — they're never in the
  compactable message list.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace, field
from typing import AsyncGenerator

from litellm.types.utils import Message, StreamingChatCompletionChunk, ChatCompletionMessageToolCall, Function

from src.types import (
    Event, TurnStart, ContentDelta, ReasoningDelta,
    CompactionEvent, ToolsReady, QueryComplete,
    CompactionContext, QueryDeps,
)
from src.api.retry import stream_with_retry, PromptTooLongError, ModelUnavailableError
from src.tools.types import ToolCall
from src.constants import MAX_OUTPUT_RECOVERY_LIMIT, ESCALATED_MAX_TOKENS, BLOCKING_BUFFER
from src.hooks import HookEvent


@dataclass
class _LoopState:
    messages: list[Message]
    turn: int = 0
    max_output_override: int | None = None
    max_output_recovery_count: int = 0
    compaction_tracking: object = None
    transition: str | None = None


@dataclass
class _ResponseAcc:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = ""


def _is_aborted(abort_signal: object) -> bool:
    return bool(abort_signal and getattr(abort_signal, "is_set", False))


async def query(
    messages: list[Message],
    system_prompt: str,
    system_context: dict[str, str],
    user_context: dict[str, str],
    deps: QueryDeps,
    max_turns: int = 20,
    max_output_tokens: int = 16_384,
) -> AsyncGenerator[Event, None]:
    """Core agent loop. Yields events, ends with QueryComplete."""

    # Build system message ONCE (system_prompt + system_context are session-stable)
    system_msg = Message(role="system", content=_build_system_prompt(system_prompt, system_context))

    # Build user_context messages ONCE (content is session-stable)
    # These are prepended to EACH API call but never stored in state.messages
    user_context_msgs = _build_user_context_messages(user_context)

    state = _LoopState(messages=list(messages))

    while state.turn < max_turns:
        state = replace(state, turn=state.turn + 1)
        yield TurnStart(turn=state.turn)

        # ── Compaction (operates on state.messages only — user_context is outside) ──

        api_for_count = [system_msg, *user_context_msgs, *state.messages]
        token_count = deps.client.count_tokens(api_for_count, deps.tool_schemas)

        ctx = CompactionContext(
            messages=state.messages,
            token_count=token_count,
            context_limit=deps.context_limit,
            client=deps.client,
            compaction_tracking=state.compaction_tracking,
        )

        for stage in deps.compaction_stages:
            result = await stage(ctx)
            if result.deleted_count > 0:
                ctx.messages = result.messages
                ctx.token_count = deps.client.count_tokens(
                    [system_msg, *user_context_msgs, *ctx.messages], deps.tool_schemas
                )
                yield CompactionEvent(stage=result.stage_name, deleted_count=result.deleted_count)
            if result.tracking is not None:
                ctx.compaction_tracking = result.tracking

        state = replace(state, messages=ctx.messages, compaction_tracking=ctx.compaction_tracking)

        # ── Build API messages ─────────────────────────────────────────────

        api_messages = [system_msg, *user_context_msgs, *state.messages]
        token_count = ctx.token_count  # reuse from compaction (already recounted if compacted)

        # ── Blocking limit ─────────────────────────────────────────────────

        if token_count >= deps.context_limit - BLOCKING_BUFFER:
            yield QueryComplete(reason="blocking_limit", turn_count=state.turn, messages=state.messages)
            return

        # ── Stream LLM ────────────────────────────────────────────────────

        if _is_aborted(deps.abort_signal):
            yield QueryComplete(reason="aborted", turn_count=state.turn, messages=state.messages)
            return

        acc = _ResponseAcc()
        max_tok = state.max_output_override or max_output_tokens

        try:
            async for chunk in stream_with_retry(deps.client, api_messages, deps.tool_schemas, max_tok):
                if _is_aborted(deps.abort_signal):
                    yield QueryComplete(reason="aborted", turn_count=state.turn, messages=state.messages)
                    return
                event = _handle_chunk(chunk, acc)
                if event is not None:
                    yield event
        except ModelUnavailableError as e:
            yield QueryComplete(reason="model_error", error=str(e), turn_count=state.turn, messages=state.messages)
            return
        except PromptTooLongError:
            yield QueryComplete(reason="prompt_too_long", turn_count=state.turn, messages=state.messages)
            return
        except Exception as e:
            yield QueryComplete(reason="model_error", error=str(e), turn_count=state.turn, messages=state.messages)
            return

        # ── No tool calls → recovery or complete ──────────────────────────

        if not acc.tool_calls:
            if not acc.text and state.max_output_override is None:
                state = replace(state, max_output_override=ESCALATED_MAX_TOKENS,
                                transition="max_output_tokens_escalate")
                continue

            if not acc.text and state.max_output_recovery_count < MAX_OUTPUT_RECOVERY_LIMIT:
                state = replace(
                    state,
                    messages=[*state.messages, Message(role="user",
                        content="Output limit hit. Resume directly — no recap. Break into smaller pieces.")],
                    max_output_recovery_count=state.max_output_recovery_count + 1,
                    transition="max_output_tokens_recovery",
                )
                continue

            if not acc.text:
                yield QueryComplete(reason="max_output_exhausted", turn_count=state.turn, messages=state.messages)
                return

            blocked = False
            stop_results = await deps.hooks.dispatch(HookEvent.STOP, {
                "messages": state.messages, "text": acc.text,
            })
            for r in stop_results:
                if r is True:
                    blocked = True
                    break
            if blocked:
                state = replace(state, transition="stop_hook_blocking")
                continue

            state = replace(state, messages=[*state.messages, Message(role="assistant", content=acc.text)])
            yield QueryComplete(reason="completed", text=acc.text, turn_count=state.turn, messages=state.messages)
            return

        # ── Tool execution (two phases) ──────────────────────────────────

        if _is_aborted(deps.abort_signal):
            yield QueryComplete(reason="aborted", turn_count=state.turn, messages=state.messages)
            return

        assistant_msg = _build_assistant_message(acc)
        parsed_calls: list[ToolCall] = []
        for tc in acc.tool_calls:
            params = _safe_json(tc.get("arguments", "{}"))
            parsed_calls.append(ToolCall(id=tc["id"], name=tc["name"], params=params))

        executor = deps.tool_executor

        # Phase 1: Permission (sequential) — executor yields rejected/running events
        async for event in executor.submit(parsed_calls):
            yield event

        # Signal UI: all tools submitted, force-render ⏳ before execution starts
        if executor.approved_count > 0:
            yield ToolsReady(count=executor.approved_count)
            # Minimum display time so ⏳ is visible even for fast tools
            await asyncio.sleep(0.15)

        # Phase 2: Execution (concurrent) — executor yields completed/error events
        async for event, _result in executor.drain():
            yield event

        # Collect all tool messages (rejected + completed) from executor
        tool_messages = executor.collect_tool_messages()

        state = replace(
            state,
            messages=[*state.messages, assistant_msg, *tool_messages],
            max_output_override=None,
            max_output_recovery_count=0,
            transition="next_turn",
        )

    yield QueryComplete(reason="max_turns", turn_count=state.turn, messages=state.messages)


# ━━ Helpers ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_system_prompt(base: str, system_context: dict[str, str]) -> str:
    if not system_context:
        return base
    lines = "\n".join(f"- {k}: {v}" for k, v in system_context.items())
    return f"{base}\n\n## System Context\n{lines}"


def _build_user_context_messages(user_context: dict[str, str]) -> list[Message]:
    """Build user_context as a single user message, prepended to each API call.

    NOT stored in state.messages — lives outside compactable history.
    No paired assistant ack — unnecessary for the first turn, and the model
    handles unpaired context messages fine when they precede the real conversation.
    """
    parts: list[str] = []
    for key, value in user_context.items():
        if value:
            parts.append(f"## {key}\n\n{value}")
    if not parts:
        return []
    return [Message(role="user", content="\n\n".join(parts))]


def _handle_chunk(chunk: StreamingChatCompletionChunk, acc: _ResponseAcc) -> Event | None:
    if not getattr(chunk, "choices", None):
        return None
    choice = chunk.choices[0]
    delta = choice.delta
    if delta.content:
        acc.text += delta.content
        return ContentDelta(text=delta.content)
    rc = getattr(delta, "reasoning_content", None)
    if rc:
        acc.reasoning += rc
        return ReasoningDelta(text=rc)
    for tc_delta in getattr(delta, "tool_calls", None) or []:
        idx = tc_delta.index
        while len(acc.tool_calls) <= idx:
            acc.tool_calls.append({"id": "", "name": "", "arguments": ""})
        entry = acc.tool_calls[idx]
        if tc_delta.id:
            entry["id"] = tc_delta.id
        fn = tc_delta.function
        if fn:
            if fn.name:
                entry["name"] += fn.name
            if fn.arguments:
                entry["arguments"] += fn.arguments
    if choice.finish_reason:
        acc.finish_reason = choice.finish_reason
    return None


def _build_assistant_message(acc: _ResponseAcc) -> Message:
    msg = Message(role="assistant", content=acc.text or "")
    msg.tool_calls = [
        ChatCompletionMessageToolCall(
            id=tc["id"],
            type="function",
            function=Function(name=tc["name"], arguments=tc["arguments"]),
        )
        for tc in acc.tool_calls
    ]
    return msg


def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}
