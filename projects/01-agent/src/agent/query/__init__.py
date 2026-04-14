"""Query module — core agent loop following Claude Code's query.ts architecture.

Exports:
- agent_loop: the main AsyncGenerator
- QueryParams, QueryDeps, LoopState, Transition, Terminal types
- StreamEvent types from types.py
"""

from .loop import agent_loop
from .params import QueryParams
from .deps import QueryDeps
from .state import (
    LoopState,
    Transition,
    Terminal,
)
from src.context.compact import AutoCompactTracking
from .types import (
    StreamEvent,
    TurnStart,
    TextEvent,
    ToolStartEvent,
    ToolResultEvent,
    StreamEnd,
    FinalEvent,
    ErrorEvent,
    ChunkAccumulator,
    handle_chunk,
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
    "StreamEvent",
    "TurnStart",
    "TextEvent",
    "ToolStartEvent",
    "ToolResultEvent",
    "StreamEnd",
    "FinalEvent",
    "ErrorEvent",
    "ChunkAccumulator",
    "handle_chunk",
    "handle_next_turn",
    "handle_collapse_drain_retry",
    "handle_reactive_compact_retry",
    "handle_max_output_tokens_escalate",
    "handle_max_output_tokens_recovery",
    "handle_stop_hook_blocking",
    "handle_token_budget_continuation",
]
