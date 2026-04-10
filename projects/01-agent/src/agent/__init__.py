"""Agent module — public API.

Re-exports:
- Agent, AgentConfig from loop.py
- StreamEvent types from types.py
- RetryConfig, RetryState from retry.py
- AgentDeps (alias QueryDeps) from query/deps.py
"""

from src.agent.loop import Agent, AgentConfig
from src.agent.types import (
    StreamEvent,
    TurnStart,
    TextEvent,
    ToolStartEvent,
    ToolResultEvent,
    StreamEnd,
    FinalEvent,
    ErrorEvent,
)
from src.agent.retry import RetryConfig, RetryState
from src.query.deps import AgentDeps

__all__ = [
    # Core
    "Agent",
    "AgentConfig",
    # Types
    "StreamEvent",
    "TurnStart",
    "TextEvent",
    "ToolStartEvent",
    "ToolResultEvent",
    "StreamEnd",
    "FinalEvent",
    "ErrorEvent",
    # Retry
    "RetryConfig",
    "RetryState",
    # Deps
    "AgentDeps",
]
