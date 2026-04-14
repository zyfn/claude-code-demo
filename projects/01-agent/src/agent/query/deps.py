"""Query dependencies — following Claude Code's QueryDeps pattern.

All external I/O and platform dependencies are passed as a single QueryDeps
dataclass, enabling tests to inject fakes without module-spy boilerplate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from litellm.types.utils import Message, StreamingChatCompletionChunk
    from src.llm.client import LLMClientProtocol
    from src.tools.base import BaseTool
    from src.tools.executor import ToolResult
    from src.context.compact import AutoCompactResult
    from .retry import RetryConfig


@dataclass
class QueryDeps:
    """All external dependencies for the query loop."""

    # LLM
    call_model: Callable[
        ["list[Message]", list[dict] | None, int | None],
        Awaitable["AsyncGenerator[StreamingChatCompletionChunk, None]"],
    ]
    count_tokens: Callable[["list[Message]", list[dict] | None], int]

    # Tools
    get_tool_schemas: Callable[[], list[dict]]
    get_tools: Callable[[], dict[str, "BaseTool"]]
    execute_tool: Callable[[str, dict, str], Awaitable["ToolResult"]]

    # Context compaction
    microcompact: Callable[["list[Message]"], tuple["list[Message]", int]]
    """Deduplicate tool results by tool_call_id."""
    autocompact: Callable[["list[Message]", "LLMClientProtocol | None"], Awaitable["AutoCompactResult | None"]]
    """LLM summarization when token threshold exceeded."""

    # Optional
    llm_client: "LLMClientProtocol | None" = None
    resolve_limit: Callable[[], int] | None = None
    retry_config: "RetryConfig | None" = None
    agent_name: str = "agent"
