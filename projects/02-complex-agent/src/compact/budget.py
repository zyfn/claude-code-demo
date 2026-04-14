"""Compaction stage: truncate oversized tool results."""

from __future__ import annotations

from litellm.types.utils import Message

from src.types import CompactionContext, CompactionResult
from src.constants import TOOL_RESULT_BUDGET


async def budget_stage(ctx: CompactionContext) -> CompactionResult:
    result: list[Message] = []
    truncated = 0
    for msg in ctx.messages:
        if msg.role != "tool":
            result.append(msg)
            continue
        content = msg.content if isinstance(msg.content, str) else ""
        if len(content) > TOOL_RESULT_BUDGET:
            result.append(Message(
                role="tool",
                content=content[:TOOL_RESULT_BUDGET] + f"\n[truncated: {len(content)} chars]",
                tool_call_id=msg.tool_call_id,
            ))
            truncated += 1
        else:
            result.append(msg)
    return CompactionResult(messages=result, deleted_count=truncated, stage_name="budget")
