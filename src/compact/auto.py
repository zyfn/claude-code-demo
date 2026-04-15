"""Compaction stage: LLM summarization when context approaches limit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from litellm.types.utils import Message

from src.types import CompactionContext, CompactionResult
from src.constants import AUTO_COMPACT_BUFFER, AUTO_COMPACT_MAX_FAILURES

if TYPE_CHECKING:
    from src.api.client import LLMClient

SUMMARIZE_PROMPT = (
    "Summarize the conversation concisely, preserving key facts, "
    "decisions, tool results, and outstanding tasks. Technical tone.\n\n"
)


@dataclass(slots=True)
class CompactionTracking:
    compacted: bool = False
    consecutive_failures: int = 0


async def auto_stage(ctx: CompactionContext) -> CompactionResult:
    tracking: CompactionTracking | None = ctx.compaction_tracking

    if tracking and tracking.consecutive_failures >= AUTO_COMPACT_MAX_FAILURES:
        return CompactionResult(messages=ctx.messages, deleted_count=0, stage_name="auto")
    if ctx.token_count < ctx.context_limit - AUTO_COMPACT_BUFFER:
        return CompactionResult(messages=ctx.messages, deleted_count=0, stage_name="auto")

    boundary = _find_boundary(ctx.messages)
    if boundary <= 1:
        return CompactionResult(messages=ctx.messages, deleted_count=0, stage_name="auto")

    to_summarize, tail = ctx.messages[:boundary], ctx.messages[boundary:]
    try:
        summary = await _summarize(ctx.client, to_summarize)
    except Exception:
        failures = (tracking.consecutive_failures + 1) if tracking else 1
        return CompactionResult(
            messages=ctx.messages, deleted_count=0,
            tracking=CompactionTracking(False, failures), stage_name="auto",
        )

    compact_msg = Message(role="system", content=f"[Conversation summary: {summary}]")
    return CompactionResult(
        messages=[compact_msg, *tail], deleted_count=len(to_summarize),
        tracking=CompactionTracking(True, 0), stage_name="auto",
    )


def _find_boundary(messages: list[Message]) -> int:
    if len(messages) <= 4:
        return 0
    tool_indices = [i for i, m in enumerate(messages) if m.role == "tool"]
    if len(tool_indices) >= 4:
        return tool_indices[-4]
    return max(1, len(messages) // 2)


async def _summarize(client: "LLMClient", messages: list[Message]) -> str:
    parts = [f"[{m.role}]: {(m.content if isinstance(m.content, str) else str(m.content))[:2000]}" for m in messages]
    text = ""
    async for chunk in client.stream(
        [Message(role="user", content=SUMMARIZE_PROMPT + "\n\n".join(parts))], max_tokens=1024,
    ):
        if hasattr(chunk, "choices") and chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text += delta.content
    return text.strip()
