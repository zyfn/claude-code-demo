"""Compaction stage: deduplicate tool results by tool_call_id."""

from __future__ import annotations

from src.types import CompactionContext, CompactionResult


async def micro_stage(ctx: CompactionContext) -> CompactionResult:
    seen: dict[str, int] = {}
    to_remove: set[int] = set()
    for i, msg in enumerate(ctx.messages):
        if msg.role == "tool" and msg.tool_call_id:
            if msg.tool_call_id in seen:
                to_remove.add(seen[msg.tool_call_id])
            seen[msg.tool_call_id] = i
    if not to_remove:
        return CompactionResult(messages=ctx.messages, deleted_count=0, stage_name="micro")
    msgs = [msg for i, msg in enumerate(ctx.messages) if i not in to_remove]
    return CompactionResult(messages=msgs, deleted_count=len(to_remove), stage_name="micro")
