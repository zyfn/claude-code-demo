"""Stream event types for the agent loop.

These are the events yielded by agent_loop() and consumed directly by
the caller (TUI, headless engine, tests). No intermediate event bus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from litellm.types.utils import StreamingChatCompletionChunk


# ─── Stream Events ────────────────────────────────────────────────────────────

@dataclass
class TurnStart:
    """Start of a new agent turn."""
    type: str = "turn_start"
    turn: int = 0


@dataclass
class TextEvent:
    """A text/reasoning content fragment from the model."""
    type: str = "content"  # "content" or "reasoning"
    text: str = ""


@dataclass
class ToolStartEvent:
    """A tool call is about to execute."""
    type: str = "tool_start"
    name: str = ""
    params: dict = field(default_factory=dict)


@dataclass
class ToolResultEvent:
    """Result from a tool execution."""
    type: str = "tool_result"
    name: str = ""
    output: str = ""
    is_error: bool = False


@dataclass
class StreamEnd:
    """End of the LLM stream for a turn."""
    type: str = "stream_end"
    stop_reason: str = ""
    accumulated_text: str = ""
    accumulated_tool_calls: list[dict] = field(default_factory=list)
    usage: dict | None = None


@dataclass
class FinalEvent:
    """Agent has completed (no more turns)."""
    type: str = "final"
    text: str = ""
    reason: str = ""  # "completed", "max_turns", "error", "model_fallback"


@dataclass
class ErrorEvent:
    """A non-recoverable error occurred."""
    type: str = "error"
    message: str = ""
    reason: str = ""


# Union type of all possible events
StreamEvent = Union[
    TurnStart,
    TextEvent,
    ToolStartEvent,
    ToolResultEvent,
    StreamEnd,
    FinalEvent,
    ErrorEvent,
]


# ─── Internal chunk handler state ─────────────────────────────────────────────

@dataclass
class ChunkAccumulator:
    """Accumulates streaming chunks into a complete response."""
    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict | None = None


def handle_chunk(
    chunk: StreamingChatCompletionChunk,
    acc: ChunkAccumulator,
) -> StreamEvent | None:
    """Handle a single streaming chunk. Returns event to yield or None."""
    if getattr(chunk, "usage", None):
        acc.usage = {
            "prompt_tokens": chunk.usage.prompt_tokens,
            "completion_tokens": chunk.usage.completion_tokens,
            "total_tokens": chunk.usage.total_tokens,
        }

    if not getattr(chunk, "choices", None):
        return None

    choice = chunk.choices[0]
    delta = choice.delta

    # Text content
    if delta.content:
        return TextEvent(type="content", text=delta.content)

    # Reasoning content
    rc = getattr(delta, "reasoning_content", None)
    if rc:
        acc.reasoning += rc
        return TextEvent(type="reasoning", text=rc)

    # Tool calls — accumulate into entries
    for tc_delta in getattr(delta, "tool_calls", None) or []:
        idx = tc_delta.index
        fn = tc_delta.function

        while len(acc.tool_calls) <= idx:
            acc.tool_calls.append({"id": "", "name": "", "arguments": ""})

        entry = acc.tool_calls[idx]
        if tc_delta.id:
            entry["id"] = tc_delta.id
        if fn:
            if fn.name:
                entry["name"] += fn.name
            if fn.arguments:
                entry["arguments"] += fn.arguments

    # End of stream
    if choice.finish_reason:
        return StreamEnd(
            type="stream_end",
            stop_reason=choice.finish_reason or "stop",
            accumulated_text=acc.text,
            accumulated_tool_calls=list(acc.tool_calls),
            usage=acc.usage,
        )

    return None
