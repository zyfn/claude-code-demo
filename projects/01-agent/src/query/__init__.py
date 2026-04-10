"""Query module — core agent loop following Claude Code's query.ts architecture.

Exports:
- agent_loop: the main AsyncGenerator
- QueryParams, QueryDeps, LoopState, Transition, Terminal types
"""

from __future__ import annotations

from .core import agent_loop
from .params import QueryParams
from .deps import QueryDeps
from .state import (
    LoopState,
    Transition,
    Terminal,
    AutoCompactTracking,
)
from .transitions import (
    handle_next_turn,
    handle_collapse_drain_retry,
    handle_reactive_compact_retry,
    handle_max_output_tokens_escalate,
    handle_max_output_tokens_recovery,
    handle_stop_hook_blocking,
    handle_token_budget_continuation,
)

__all__ = [
    "agent_loop",
    "QueryParams",
    "QueryDeps",
    "LoopState",
    "Transition",
    "Terminal",
    "AutoCompactTracking",
    "handle_next_turn",
    "handle_collapse_drain_retry",
    "handle_reactive_compact_retry",
    "handle_max_output_tokens_escalate",
    "handle_max_output_tokens_recovery",
    "handle_stop_hook_blocking",
    "handle_token_budget_continuation",
]
