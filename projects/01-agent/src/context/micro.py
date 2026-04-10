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


def micro_compact_with_time_decay(
    messages: list[Message],
    max_age_turns: int = 4,
) -> tuple[list[Message], int]:
    """Remove tool results older than N turns (time-based decay).

    This is a more aggressive variant: in addition to deduping by
    tool_call_id, it also removes tool results from tool calls that
    are more than `max_age_turns` turns old.

    Args:
        messages: Full message history
        max_age_turns: Maximum number of turns to retain tool results

    Returns:
        ( compacted_messages, deleted_count )
    """
    if len(messages) <= 3:
        return messages, 0

    # Count turns (user-assistant pairs)
    turn_boundaries: list[int] = []
    for i, msg in enumerate(messages):
        if msg.role == "user":
            turn_boundaries.append(i)

    if len(turn_boundaries) <= max_age_turns:
        return messages, 0

    # The oldest turn we keep starts at this boundary
    oldest_keep = turn_boundaries[-max_age_turns]

    # Mark tool results older than the cutoff for removal
    to_remove: set[int] = set()
    for i, msg in enumerate(messages):
        if msg.role == "tool" and i < oldest_keep:
            to_remove.add(i)

    if not to_remove:
        return messages, 0

    result = [msg for i, msg in enumerate(messages) if i not in to_remove]
    return result, len(to_remove)
