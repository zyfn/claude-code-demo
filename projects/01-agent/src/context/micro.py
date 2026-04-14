"""Level 3 compression: micro_compact.

Mirrors Claude Code's microcompact.ts. Deduplicates tool results by
tool_call_id, keeping only the most recent occurrence. This prevents
stale cached reads from consuming context budget.

Unlike the old regex-based heuristic ("Reading <path>"), this uses
tool_call_id directly, which is stable and unambiguous.
"""

from __future__ import annotations

from litellm.types.utils import Message


def micro_compact(messages: list[Message]) -> tuple[list[Message], int]:
    """Remove duplicate tool results, keeping only the most recent.

    Uses tool_call_id as the deduplication key — a stable identifier
    assigned by the LLM at tool call time.

    Args:
        messages: Full message history

    Returns:
        ( compacted_messages, deleted_count )
    """
    # Track last occurrence of each tool_call_id
    seen: dict[str, int] = {}  # tool_call_id → last message index
    to_remove: set[int] = set()

    for i, msg in enumerate(messages):
        if msg.role == "tool" and msg.tool_call_id:
            tc_id = msg.tool_call_id
            if tc_id in seen:
                # Mark earlier occurrence for removal
                to_remove.add(seen[tc_id])
            seen[tc_id] = i

    if not to_remove:
        return messages, 0

    # Build new list, skipping removed indices
    result = [msg for i, msg in enumerate(messages) if i not in to_remove]
    return result, len(to_remove)
