"""Level 4/5 compression: auto_compact.

Mirrors Claude Code's autoCompact.ts — LLM summarization when context
approaches the limit. Threshold formula: limit * ratio - buffer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from litellm.types.utils import Message

if TYPE_CHECKING:
    from src.llm.client import LLMClientProtocol


AUTO_COMPACT_BUFFER = 13_000
MAX_CONSECUTIVE_FAILURES = 3

DEFAULT_SUMMARIZE_PROMPT = (
    "Summarize the conversation concisely, preserving key facts and decisions. "
    "Use a neutral, technical tone:\n\n"
)


@dataclass
class AutoCompactResult:
    summary: str
    post_compact_messages: list[Message]
    tracking: "AutoCompactTracking"
    deleted_count: int
    pre_compact_token_count: int
    post_compact_token_count: int


@dataclass
class AutoCompactTracking:
    """Tracks auto-compaction state across iterations (circuit breaker).

    Prevents infinite compaction loops by tracking consecutive failures.
    """
    compacted: bool = False
    turn_id: str = ""
    turn_counter: int = 0
    consecutive_failures: int = 0


def should_auto_compact(
    messages: list[Message],
    count_tokens: Callable[[list[Message], list[dict] | None], int],
    resolve_limit: Callable[[], int],
    tracking: "AutoCompactTracking | None",
    ratio: float = 0.8,
) -> bool:
    """Return True if auto-compaction should run.

    Threshold: current_tokens >= limit * ratio - buffer
    Circuit breaker: skip if consecutive_failures >= MAX_CONSECUTIVE_FAILURES.
    """
    if tracking and tracking.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return False
    limit = resolve_limit()
    current = count_tokens(messages, None)
    threshold = int(limit * ratio) - AUTO_COMPACT_BUFFER
    return current >= threshold


async def auto_compact(
    messages: list[Message],
    count_tokens: Callable[[list[Message], list[dict] | None], int],
    llm_client: "LLMClientProtocol | None",
    resolve_limit: Callable[[], int],
    tracking: "AutoCompactTracking | None",
    ratio: float = 0.8,
) -> AutoCompactResult | None:
    """Compact old messages via LLM summarization.

    Splits at tool_call_id boundary, summarizes middle section,
    replaces with [Earlier conversation summarized: ...] marker.
    """
    if llm_client is None:
        return None

    if not should_auto_compact(messages, count_tokens, resolve_limit, tracking, ratio):
        return None

    boundary = _find_compact_boundary(messages)
    if boundary <= 1:
        return None

    to_summarize = messages[1:boundary]
    if not to_summarize:
        return None

    pre_count = count_tokens(messages, None)

    try:
        summary = await _generate_summary(llm_client, to_summarize, DEFAULT_SUMMARIZE_PROMPT)
    except Exception:
        new_failures = (tracking.consecutive_failures + 1) if tracking else 1
        new_tracking = AutoCompactTracking(
            compacted=False,
            turn_id=tracking.turn_id if tracking else "",
            turn_counter=0,
            consecutive_failures=new_failures,
        )
        return AutoCompactResult(
            summary="",
            post_compact_messages=messages,
            tracking=new_tracking,
            deleted_count=0,
            pre_compact_token_count=pre_count,
            post_compact_token_count=pre_count,
        )

    compact_msg = Message(role="system", content=f"[Earlier conversation summarized: {summary}]")
    post_compact = [messages[0], compact_msg] + messages[boundary:]
    post_count = count_tokens(post_compact, None)

    new_tracking = AutoCompactTracking(
        compacted=True,
        turn_id=str(uuid.uuid4()),
        turn_counter=0,
        consecutive_failures=0,
    )

    return AutoCompactResult(
        summary=summary,
        post_compact_messages=post_compact,
        tracking=new_tracking,
        deleted_count=len(to_summarize),
        pre_compact_token_count=pre_count,
        post_compact_token_count=post_count,
    )


def _find_compact_boundary(messages: list[Message]) -> int:
    """Find index to split at — after system prompt, before last ~2 turns."""
    if len(messages) <= 3:
        return 0
    tool_indices = [i for i, m in enumerate(messages) if m.role == "tool"]
    if not tool_indices:
        return len(messages) // 2
    if len(tool_indices) >= 4:
        return max(1, tool_indices[-4])
    return max(1, tool_indices[-2] if tool_indices else 1)


async def _generate_summary(
    client: "LLMClientProtocol",
    messages: list[Message],
    prompt: str,
    max_tokens: int = 1024,
) -> str:
    """Generate summary via LLM."""
    from litellm.types.utils import Message as LLMMessage

    body = "\n\n".join(f"[{m.role}]: {_get_content(m)}" for m in messages)
    summary_messages = [
        LLMMessage(role="user", content=prompt),
        LLMMessage(role="user", content=body),
    ]

    text = ""
    async for chunk in client.chat(summary_messages, max_tokens=max_tokens):
        if hasattr(chunk, "choices") and chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text += delta.content
    return text.strip()


def _get_content(msg: Message) -> str:
    if isinstance(msg.content, str):
        return msg.content
    if isinstance(msg.content, list):
        return "".join(c.text for c in msg.content if hasattr(c, "text"))
    return ""
