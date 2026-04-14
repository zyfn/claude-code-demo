"""Agent module — high-level public API.

Mirrors Claude Code's agent/ directory:
- Agent class, AgentConfig: high-level agent API
- query/ submodule: core ReAct loop (agent/query.ts)

Re-exports:
- Agent, AgentConfig from .agent
- StreamEvent types from .query.types
- RetryConfig, RetryState from .query.retry
"""

from .agent import Agent, AgentConfig
from .query.retry import RetryConfig, RetryState
from .query.types import (
    StreamEvent,
    TurnStart,
    TextEvent,
    ToolStartEvent,
    ToolResultEvent,
    StreamEnd,
    FinalEvent,
    ErrorEvent,
)

__all__ = [
    "Agent",
    "AgentConfig",
    "StreamEvent",
    "TurnStart",
    "TextEvent",
    "ToolStartEvent",
    "ToolResultEvent",
    "StreamEnd",
    "FinalEvent",
    "ErrorEvent",
    "RetryConfig",
    "RetryState",
]
