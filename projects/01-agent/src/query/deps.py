"""Query dependencies — following Claude Code's QueryDeps pattern.

All external I/O and platform dependencies are passed as a single QueryDeps
dataclass, enabling tests to inject fakes without module-spy boilerplate.

Usage:
    deps = QueryDeps(
        call_model=my_client.chat,
        count_tokens=my_client.count_tokens,
        execute_tool=executor.execute,
        microcompact=context_manager.micro_compact,
        autocompact=context_manager.auto_compact,
        ...
    )
    async for event in agent_loop(params, deps):
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
class QueryDeps:
    """All external dependencies for the query loop.

    Mirrors Claude Code's QueryDeps. Separates micro_compact and auto_compact
    as distinct dependencies (called at different pipeline stages) rather
    than a single combined apply_context_compactions.
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

    # ── Context compaction ───────────────────────────────────────────────────

    microcompact: Callable[
        [list[Message]], tuple[list[Message], int]
    ]
    """Micro-compact: deduplicate tool results. Returns (messages, deleted_count)."""

    autocompact: Callable[
        [list[Message], Any], Awaitable[dict | None]
    ]
    """Auto-compact: LLM summarization when token threshold exceeded.
    Returns compaction result dict or None if skipped.
    (Any = LLMClientProtocol | None at call site)"""

    llm_client: "LLMClientProtocol | None" = None
    """LLM client for auto-compaction summarization."""

    resolve_limit: Callable[[], int] | None = None
    """Resolve the model's context limit. Used by compaction threshold checks."""

    # ── Retry ────────────────────────────────────────────────────────────────

    retry_config: "RetryConfig | None" = None
    """Retry configuration. None means use defaults."""

    # ── Identity ────────────────────────────────────────────────────────────

    agent_name: str = "agent"
    """Name of this agent (for logging/analytics)."""


# Alias for backwards compatibility
AgentDeps = QueryDeps
