"""Query parameters — input to the agent loop.

Mirrors Claude Code's QueryParams: a single immutable object carrying
all configuration and dependencies for a query session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litellm.types.utils import Message
    from .deps import QueryDeps


@dataclass
class QueryParams:
    """All parameters for a single query/agent session.

    This is the single input object passed to agent_loop(), mirroring
    Claude Code's QueryParams. It is immutable after construction.

    Fields:
        messages: Initial conversation history (system prompt is NOT included here;
                 it is passed separately via system_prompt).
        system_prompt: Static role + guidelines string.
        system_context: Dynamic key-value pairs injected into system prompt
                        at each API call (e.g. git_status, cache_breaker).
        user_context: Dynamic key-value pairs prepended to user messages
                      (e.g. claude_md, current_date).
        max_turns: Upper bound on iterations before loop exits.
        max_output_tokens: Max tokens for model output per turn.
        deps: All external dependencies (LLM client, tools, compaction, etc.).
    """
    messages: list[Message]
    system_prompt: str
    system_context: dict[str, str]  # e.g. { git_status: "...", cache_breaker: "..." }
    user_context: dict[str, str]  # e.g. { claude_md: "...", current_date: "2026/04/10" }
    max_turns: int = 20
    max_output_tokens: int = 8192
    deps: "QueryDeps | None" = None
