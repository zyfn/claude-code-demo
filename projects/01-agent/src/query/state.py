"""Loop state types — LoopState, Transition, Terminal, AutoCompactTracking.

Following Claude Code's state management pattern: the entire state is replaced
on each iteration (whole-state replacement), never mutated in place.
This makes state transitions explicit and traceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litellm.types.utils import Message


# ─── Transition — 7 种 continue 原因 ─────────────────────────────────────────

class Transition:
    """Tagged union for loop continuation reasons.

    Each reason carries different payload:
    - next_turn: normal tool execution → next iteration
    - collapse_drain_retry: commit pending collapse then retry
    - reactive_compact_retry: reactive compact succeeded → retry with compact messages
    - max_output_tokens_escalate: escalate max_tokens 8k→64k → retry
    - max_output_tokens_recovery: inject recovery prompt → retry
    - stop_hook_blocking: stop hook returned blocking error → retry with error injected
    - token_budget_continuation: token budget not exhausted → inject nudge → continue
    """

    __slots__ = ("reason", "committed", "attempt")

    def __init__(
        self,
        reason: str,
        committed: int = 0,
        attempt: int = 0,
    ):
        self.reason = reason  # 'next_turn' | 'collapse_drain_retry' | ...
        self.committed = committed  # used by collapse_drain_retry
        self.attempt = attempt  # used by max_output_tokens_recovery

    # Convenience constructors for each reason
    @classmethod
    def next_turn(cls) -> "Transition":
        return cls(reason="next_turn")

    @classmethod
    def collapse_drain_retry(cls, committed: int) -> "Transition":
        return cls(reason="collapse_drain_retry", committed=committed)

    @classmethod
    def reactive_compact_retry(cls) -> "Transition":
        return cls(reason="reactive_compact_retry")

    @classmethod
    def max_output_tokens_escalate(cls) -> "Transition":
        return cls(reason="max_output_tokens_escalate")

    @classmethod
    def max_output_tokens_recovery(cls, attempt: int) -> "Transition":
        return cls(reason="max_output_tokens_recovery", attempt=attempt)

    @classmethod
    def stop_hook_blocking(cls) -> "Transition":
        return cls(reason="stop_hook_blocking")

    @classmethod
    def token_budget_continuation(cls) -> "Transition":
        return cls(reason="token_budget_continuation")

    def __repr__(self) -> str:
        return f"Transition(reason={self.reason!r}, committed={self.committed}, attempt={self.attempt})"


# ─── Terminal — loop 返回类型 ─────────────────────────────────────────────────

@dataclass
class Terminal:
    """Return type of the agent_loop AsyncGenerator.

    Represents the final outcome of the loop:
    - completed: normal completion (no tool calls produced)
    - max_turns: iteration limit reached
    - model_error: unrecoverable model error
    - prompt_too_long: prompt too long after all recovery attempts
    - blocking_limit: token count at blocking threshold before API call
    - aborted_streaming: streaming was aborted
    - aborted_tools: tool execution was aborted
    - hook_stopped: a hook prevented continuation
    - stop_hook_prevented: stop hook prevented continuation
    """
    reason: str
    error: str | None = None
    turn_count: int = 0

    # Convenience constructors
    @classmethod
    def completed(cls, turn_count: int) -> "Terminal":
        return cls(reason="completed", turn_count=turn_count)

    @classmethod
    def max_turns(cls, turn_count: int) -> "Terminal":
        return cls(reason="max_turns", turn_count=turn_count)

    @classmethod
    def model_error(cls, error: str, turn_count: int) -> "Terminal":
        return cls(reason="model_error", error=error, turn_count=turn_count)

    @classmethod
    def prompt_too_long(cls, turn_count: int) -> "Terminal":
        return cls(reason="prompt_too_long", turn_count=turn_count)

    @classmethod
    def blocking_limit(cls, turn_count: int) -> "Terminal":
        return cls(reason="blocking_limit", turn_count=turn_count)


# ─── AutoCompactTracking ────────────────────────────────────────────────────────

@dataclass
class AutoCompactTracking:
    """Tracks auto-compaction state across iterations (circuit breaker).

    Prevents infinite compaction loops by tracking consecutive failures.
    """
    compacted: bool = False
    turn_id: str = ""  # unique id for this compaction cycle
    turn_counter: int = 0  # turns since last compaction
    consecutive_failures: int = 0  # circuit breaker


# ─── LoopState ─────────────────────────────────────────────────────────────────

@dataclass
class LoopState:
    """Immutable-style state carried through the ReAct loop.

    Following Claude Code's pattern: state is replaced wholesale on each
    iteration via with_* methods, never mutated in place.
    """
    messages: list[Message]
    turn_count: int = 1
    transition: Transition | None = None
    auto_compact_tracking: AutoCompactTracking | None = None
    max_output_tokens_count: int = 0
    has_attempted_reactive_compact: bool = False
    max_output_tokens_override: int | None = None
    pending_tool_use_summary: str | None = None  # Haiku summary from prior turn
    stop_hook_active: bool = False

    def with_messages(self, messages: list[Message]) -> "LoopState":
        """Return a new state with updated messages."""
        return LoopState(
            messages=messages,
            turn_count=self.turn_count,
            transition=self.transition,
            auto_compact_tracking=self.auto_compact_tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=self.has_attempted_reactive_compact,
            max_output_tokens_override=self.max_output_tokens_override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=self.stop_hook_active,
        )

    def with_turn(self, turn_count: int) -> "LoopState":
        """Return a new state with incremented turn count."""
        return LoopState(
            messages=self.messages,
            turn_count=turn_count,
            transition=self.transition,
            auto_compact_tracking=self.auto_compact_tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=self.has_attempted_reactive_compact,
            max_output_tokens_override=self.max_output_tokens_override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=self.stop_hook_active,
        )

    def with_transition(self, transition: Transition) -> "LoopState":
        """Return a new state with updated transition."""
        return LoopState(
            messages=self.messages,
            turn_count=self.turn_count,
            transition=transition,
            auto_compact_tracking=self.auto_compact_tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=self.has_attempted_reactive_compact,
            max_output_tokens_override=self.max_output_tokens_override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=self.stop_hook_active,
        )

    def with_auto_compact_tracking(
        self, tracking: AutoCompactTracking | None
    ) -> "LoopState":
        """Return a new state with updated auto-compact tracking."""
        return LoopState(
            messages=self.messages,
            turn_count=self.turn_count,
            transition=self.transition,
            auto_compact_tracking=tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=self.has_attempted_reactive_compact,
            max_output_tokens_override=self.max_output_tokens_override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=self.stop_hook_active,
        )

    def with_max_output_override(
        self, override: int | None
    ) -> "LoopState":
        """Return a new state with updated max output tokens override."""
        return LoopState(
            messages=self.messages,
            turn_count=self.turn_count,
            transition=self.transition,
            auto_compact_tracking=self.auto_compact_tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=self.has_attempted_reactive_compact,
            max_output_tokens_override=override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=self.stop_hook_active,
        )

    def with_reactive_compact_reset(self) -> "LoopState":
        """Return a new state with has_attempted_reactive_compact reset."""
        return LoopState(
            messages=self.messages,
            turn_count=self.turn_count,
            transition=self.transition,
            auto_compact_tracking=self.auto_compact_tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=False,
            max_output_tokens_override=self.max_output_tokens_override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=self.stop_hook_active,
        )

    def with_stop_hook_active(self, active: bool) -> "LoopState":
        """Return a new state with updated stop_hook_active."""
        return LoopState(
            messages=self.messages,
            turn_count=self.turn_count,
            transition=self.transition,
            auto_compact_tracking=self.auto_compact_tracking,
            max_output_tokens_count=self.max_output_tokens_count,
            has_attempted_reactive_compact=self.has_attempted_reactive_compact,
            max_output_tokens_override=self.max_output_tokens_override,
            pending_tool_use_summary=self.pending_tool_use_summary,
            stop_hook_active=active,
        )
