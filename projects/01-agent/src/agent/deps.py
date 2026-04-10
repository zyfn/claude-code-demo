"""Dependency injection for the agent loop.

AgentDeps follows the same pattern as Claude Code's QueryDeps:
all external I/O and platform dependencies are passed as a single object,
enabling tests to inject fakes without module-spy boilerplate.

Usage:
    deps = AgentDeps(
        call_model=my_client.chat,
        count_tokens=my_client.count_tokens,
        execute_tool=executor.execute,
        ...
    )
    async for event in agent_loop(config, deps, messages):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Awaitable, Any

if TYPE_CHECKING:
    from litellm.types.utils import Message, StreamingChatCompletionChunk
    from src.llm.client import LLMClientProtocol
    from src.tools.executor import ToolResult
    from src.agent.retry import RetryConfig


@dataclass
class AgentDeps:
    """All external dependencies for the agent loop.

    This replaces the EventBus + hardcoded client + inline recovery pattern
    with explicit dependency injection.
    """

    # ── LLM ──────────────────────────────────────────────────────────────────

    call_model: Callable[
        ["list[Message]", list[dict] | None, int | None],
        Awaitable["AsyncGenerator[StreamingChatCompletionChunk, None]"],
    ]
    """Async generator of streaming response chunks."""

    count_tokens: Callable[
        ["list[Message]", list[dict] | None],
        int,
    ]
    """Count tokens in a message list."""

    # ── Tools ────────────────────────────────────────────────────────────────

    get_tool_schemas: Callable[[], list[dict]]
    """Return tool schemas for the LLM."""

    get_tools: Callable[[], dict[str, "BaseTool"]]
    """Return tool instances by name."""

    execute_tool: Callable[[str, dict, str], Awaitable["ToolResult"]]
    """Execute a single tool: (name, params, tool_call_id) -> ToolResult."""

    # ── Context ─────────────────────────────────────────────────────────────

    apply_context_compactions: Callable[
        [list[dict], Any], Awaitable[dict]
    ]
    """Apply context compaction and return stats dict."""

    llm_client: "LLMClientProtocol | None" = None
    """LLM client for Level 3 auto-compaction summarization."""

    # ── Retry ────────────────────────────────────────────────────────────────

    retry_config: "RetryConfig | None" = None
    """Retry configuration. None means use defaults."""

    # ── Identity ────────────────────────────────────────────────────────────

    agent_name: str = "agent"
    """Name of this agent (for logging/analytics)."""
