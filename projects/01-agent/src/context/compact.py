"""Level 4/5 compression: auto_compact.

Mirrors Claude Code's autoCompact.ts + compactConversation(). Proactive
full summarization using LLM when token threshold is exceeded.

Key features:
- Threshold-based: only runs when context approaches limit
- Circuit breaker: MAX_CONSECUTIVE_FAILURES prevents infinite loops
- Message replacement: old messages replaced with a single summary
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Awaitable

from litellm.types.utils import Message

if TYPE_CHECKING:
    from src.llm.client import LLMClientProtocol


# ─── Constants ─────────────────────────────────────────────────────────────────

# Claude Code uses: effectiveContextWindow - 13_000 buffer
AUTO_COMPACT_BUFFER = 13_000
MAX_CONSECUTIVE_FAILURES = 3
# Default summarization prompt
DEFAULT_SUMMARIZE_PROMPT = (
    "Summarize the following conversation concisely, preserving key facts, "
    "decisions, and any outstanding tasks. Use a neutral, technical tone:\n\n"
)


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class AutoCompactResult:
    """Result of a successful auto-compaction."""
    summary: str
    post_compact_messages: list[Message]
    tracking: "AutoCompactTracking"
    deleted_count: int
    pre_compact_token_count: int
    post_compact_token_count: int


@dataclass
class AutoCompactTracking:
    """Tracks auto-compaction state across iterations (circuit breaker)."""
    compacted: bool = False
    turn_id: str = ""
    turn_counter: int = 0
    consecutive_failures: int = 0


# ─── Threshold check ───────────────────────────────────────────────────────────

def should_auto_compact(
    messages: list[Message],
    count_tokens: Callable[[list[Message], list[dict] | None], int],
    resolve_limit: Callable[[], int],
    tracking: AutoCompactTracking | None,
    ratio: float = 0.8,
) -> bool:
    """Check if auto-compaction should run (threshold + circuit breaker).

    Args:
        messages: Current message history
        count_tokens: Token counting function
        resolve_limit: Returns the model's context limit
        tracking: Current compaction tracking state (circuit breaker)
        ratio: Target context usage ratio (0.8 = 80% of limit)

    Returns:
        True if compaction should run.
    """
    if tracking and tracking.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        # Circuit breaker open — skip
        return False

    limit = resolve_limit()
    threshold = int(limit * ratio)
    # Claude Code uses: limit - AUTO_COMPACT_BUFFER as the actual threshold
    actual_threshold = limit - AUTO_COMPACT_BUFFER

    current = count_tokens(messages, None)
    return current >= actual_threshold


# ─── Auto-compact ─────────────────────────────────────────────────────────────

async def auto_compact(
    messages: list[Message],
    count_tokens: Callable[[list[Message], list[dict] | None], int],
    llm_client: "LLMClientProtocol | None",
    resolve_limit: Callable[[], int],
    tracking: AutoCompactTracking | None,
    summary_prompt: str = DEFAULT_SUMMARIZE_PROMPT,
    ratio: float = 0.8,
) -> AutoCompactResult | None:
    """Compact old messages using LLM summarization.

    Finds a compact boundary (after system prompt, before recent messages),
    generates a summary of the middle section, and returns the new message list.

    Args:
        messages: Full message history
        count_tokens: Token counting function
        llm_client: LLM client for summarization
        resolve_limit: Returns the model's context limit
        tracking: Current compaction tracking state
        summary_prompt: Prompt template for summarization
        ratio: Target context usage ratio

    Returns:
        AutoCompactResult if successful, None if skipped or failed.
    """
    if llm_client is None:
        return None

    # Check threshold
    if not should_auto_compact(
        messages, count_tokens, resolve_limit, tracking, ratio
    ):
        return None

    # Find compact boundary: after system prompt, before recent turns
    boundary = _find_compact_boundary(messages)
    if boundary <= 1:
        return None

    messages_to_summarize = messages[1:boundary]  # Exclude system prompt
    if not messages_to_summarize:
        return None

    pre_count = count_tokens(messages, None)

    try:
        summary = await _generate_summary(
            llm_client, messages_to_summarize, summary_prompt
        )
    except Exception:
        # Failure — increment circuit breaker
        new_failures = (tracking.consecutive_failures + 1) if tracking else 1
        new_tracking = AutoCompactTracking(
            compacted=False,
            turn_id=tracking.turn_id if tracking else "",
            turn_counter=0,
            consecutive_failures=new_failures,
        )
        # Return a result with updated tracking (but no message change)
        return AutoCompactResult(
            summary="",
            post_compact_messages=messages,
            tracking=new_tracking,
            deleted_count=0,
            pre_compact_token_count=pre_count,
            post_compact_token_count=pre_count,
        )

    # Build compact message
    compact_msg = Message(
        role="system",
        content=f"[Earlier conversation summarized: {summary}]",
    )
    post_compact = [messages[0], compact_msg] + messages[boundary:]
    post_count = count_tokens(post_compact, None)

    new_tracking = AutoCompactTracking(
        compacted=True,
        turn_id=str(uuid.uuid4()),
        turn_counter=0,
        consecutive_failures=0,  # Reset on success
    )

    return AutoCompactResult(
        summary=summary,
        post_compact_messages=post_compact,
        tracking=new_tracking,
        deleted_count=len(messages_to_summarize),
        pre_compact_token_count=pre_count,
        post_compact_token_count=post_count,
    )


def _find_compact_boundary(messages: list[Message]) -> int:
    """Find a good place to split messages for compaction.

    Returns index of first message to keep (after system prompt).
    Keeps at least system + 2 messages, and aims to keep the last ~2 turns.
    """
    if len(messages) <= 3:
        return 0

    # Find tool result indices
    tool_result_indices = [
        i for i, m in enumerate(messages) if m.role == "tool"
    ]
    if not tool_result_indices:
        return len(messages) // 2

    # Keep the last 4 tool results (≈ last 2 turns)
    if len(tool_result_indices) >= 4:
        return max(1, tool_result_indices[-4])

    return max(1, tool_result_indices[-2] if tool_result_indices else 1)


async def _generate_summary(
    client: "LLMClientProtocol",
    messages: list[Message],
    prompt: str,
    max_tokens: int = 1024,
) -> str:
    """Use LLM to generate a summary of messages."""
    from litellm.types.utils import Message as LLMMessage

    summary_messages = [
        LLMMessage(role="user", content=prompt),
        LLMMessage(
            role="user",
            content="\n\n".join(
                f"[{m.role}]: {_get_content(m)}" for m in messages
            ),
        ),
    ]

    text = ""
    async for chunk in client.chat(summary_messages, max_tokens=max_tokens):
        if hasattr(chunk, "choices") and chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text += delta.content
    return text.strip()


def _get_content(msg: Message) -> str:
    """Extract string content from a Message."""
    if isinstance(msg.content, str):
        return msg.content
    if isinstance(msg.content, list):
        return "".join(c.text for c in msg.content if hasattr(c, "text"))
    return ""
