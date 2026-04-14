"""Transition handlers — 7 recovery paths.

Each function takes the current state and returns (new_state, terminal_or_continue).
If a Terminal is returned, the loop exits. If None/continue, the loop proceeds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .state import LoopState, Transition, Terminal
from .deps import QueryDeps

if TYPE_CHECKING:
    from .types import ChunkAccumulator


def handle_next_turn(state: LoopState) -> LoopState:
    """Normal tool execution → continue to next turn."""
    return state.with_transition(Transition.next_turn())


def handle_collapse_drain_retry(
    state: LoopState,
    committed: int,
) -> LoopState:
    """Collapse drain: commit pending collapses then retry.

    In our current implementation this is a stub — full context collapse
    requires a collapse store which we haven't implemented yet.
    """
    return state.with_transition(Transition(reason="collapse_drain_retry", committed=committed))


def handle_reactive_compact_retry(
    state: LoopState,
    compacted_messages: list,
) -> LoopState:
    """Reactive compact succeeded → replace messages and retry."""
    return state.with_messages(compacted_messages).with_transition(
        Transition.reactive_compact_retry()
    ).with_reactive_compact_reset()


def handle_max_output_tokens_escalate(
    state: LoopState,
    acc: "ChunkAccumulator",
    base_max_tokens: int,
    deps: QueryDeps,
    messages_for_query: list,
) -> tuple[LoopState, Terminal | None]:
    """First max_output_tokens hit: escalate 8k→64k and retry."""
    ESCALATED_MAX = 64_000

    if state.max_output_tokens_override is None:
        # First escalation
        return (
            state.with_max_output_override(ESCALATED_MAX),
            None,
        )

    # Already escalated — try recovery
    return handle_max_output_tokens_recovery(state, acc, deps, messages_for_query)


def handle_max_output_tokens_recovery(
    state: LoopState,
    acc: "ChunkAccumulator",
    deps: QueryDeps,
    messages_for_query: list,
) -> tuple[LoopState, Terminal | None]:
    """Inject recovery prompt and retry (up to 3 times)."""
    MAX_RECOVERY = 3

    if state.max_output_tokens_count >= MAX_RECOVERY:
        return state, Terminal(reason="max_output_tokens_exhausted", turn_count=state.turn_count)

    recovery_message = (
        "The model's response was cut off at the maximum output token limit. "
        "Please continue from where it left off, completing any incomplete thoughts or actions."
    )

    from litellm.types.utils import Message
    next_messages = list(state.messages) + [
        Message(role="user", content=recovery_message),
    ]

    return (
        LoopState(
            messages=next_messages,
            turn_count=state.turn_count,
            transition=Transition.max_output_tokens_recovery(state.max_output_tokens_count + 1),
            auto_compact_tracking=state.auto_compact_tracking,
            max_output_tokens_count=state.max_output_tokens_count + 1,
            has_attempted_reactive_compact=state.has_attempted_reactive_compact,
            max_output_tokens_override=state.max_output_tokens_override,
            pending_tool_use_summary=state.pending_tool_use_summary,
            stop_hook_active=state.stop_hook_active,
        ),
        None,  # continue, not terminal
    )


def handle_stop_hook_blocking(
    state: LoopState,
) -> tuple[LoopState, bool]:
    """Stop hook returned blocking error → inject error and retry.

    Stub: stop hooks are not yet implemented, always returns (state, False).
    When stop hooks are added, this should return (state_with_error, True)
    when a hook blocks the response.
    """
    return state, False


def handle_token_budget_continuation(
    state: LoopState,
) -> tuple[LoopState, Terminal | None]:
    """Token budget not exhausted → inject nudge and continue.

    Stub: token budget feature not yet implemented.
    Currently just continues without injecting anything.
    """
    return state, None
