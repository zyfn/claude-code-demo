"""High-level Agent API — wires the query loop with tools and context.

Mirrors Claude Code's agent.ts: the Agent class is the top-level public API.
It wraps the query loop (query/loop.py) with tool management, message
history, and dependency injection.

Usage:
    agent = Agent(config, client, tools)
    async for event in agent.run_stream(user_input):
        if isinstance(event, TextEvent):
            print(event.text, end="", flush=True)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncGenerator

from litellm.types.utils import Message

from src.agent.query.types import (
    StreamEvent,
    TextEvent,
    ToolStartEvent,
    ToolResultEvent,
    FinalEvent,
    TurnStart,
    ErrorEvent,
)
from src.agent.query.retry import RetryConfig
from src.tools.executor import ToolExecutor
from src.llm.client import get_model_info

if TYPE_CHECKING:
    from src.llm.client import LLMClientProtocol
    from src.tools.base import BaseTool
    from src.context.compact import AutoCompactResult


__all__ = ["Agent", "AgentConfig"]


# ─── Agent Config ──────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """Configuration for the high-level Agent API."""
    name: str = "agent"
    system_prompt: str = ""
    system_context: dict[str, str] | None = None
    user_context: dict[str, str] | None = None
    max_turns: int = 20
    max_output_tokens: int = 8192
    context_ratio: float = 0.8


# ─── High-level Agent ──────────────────────────────────────────────────────────

class Agent:
    """High-level Agent API — wires query loop + executor + context.

    Usage:
        agent = Agent(config, client, tools)
        async for event in agent.run_stream(user_input):
            if isinstance(event, TextEvent):
                print(event.text, end="", flush=True)
    """

    def __init__(
        self,
        config: AgentConfig,
        client: "LLMClientProtocol",
        tools: list["BaseTool"],
    ):
        self._config = config
        self._client = client
        self._executor = ToolExecutor(tools)
        # NOTE: system prompt is NOT stored in _messages.
        # query/core.py's _prepend_context() adds it fresh at each turn.
        self._messages: list[Message] = []

        primary_model = getattr(client, "_model", "")
        ctx_limit = get_model_info(primary_model).get("max_input_tokens", 128_000)
        self._ctx_limit = ctx_limit

    # ── Tool management ────────────────────────────────────────────────────

    def add_tool(self, tool: "BaseTool") -> None:
        self._executor.add_tool(tool)

    def remove_tool(self, name: str) -> None:
        self._executor.remove_tool(name)

    def get_tool(self, name: str) -> "BaseTool | None":
        return self._executor.get_tool(name)

    @property
    def tools(self) -> list["BaseTool"]:
        return self._executor.tools

    @property
    def message_count(self) -> int:
        return len(self._messages)

    # ── Message injection ──────────────────────────────────────────────────

    def inject_messages(self, messages: list[Message]) -> None:
        """Inject messages into the agent's message list.

        Used by skills to inject prompts into the ongoing conversation.
        """
        self._messages.extend(messages)

    # ── Streaming run ───────────────────────────────────────────────────────

    async def run_stream(
        self,
        user_input: str,
        retry_config: RetryConfig | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Run agent on user input, yielding stream events.

        The caller handles all event rendering (TUI, headless, test).
        This method does NOT emit to an EventBus — events go directly
        to the caller via async generator.
        """
        if user_input:
            self._messages.append(Message(role="user", content=user_input))

        from src.agent.query import QueryParams
        from src.agent.query.state import Terminal
        from src.agent.query.loop import agent_loop as _query_loop

        params = QueryParams(
            messages=self._messages,
            system_prompt=self._config.system_prompt,
            system_context=self._config.system_context or {},
            user_context=self._config.user_context or {},
            max_turns=self._config.max_turns,
            max_output_tokens=self._config.max_output_tokens,
            deps=self._build_deps(retry_config),
        )

        async for event in _query_loop(params):
            # Terminal events are yielded last — handle but don't forward to TUI
            if isinstance(event, Terminal):
                # Map Terminal to FinalEvent for backward compatibility
                yield FinalEvent(text=event.text, reason=event.reason)
                return
            yield event

    # ── Deps factory ───────────────────────────────────────────────────────

    def _build_deps(self, retry_config: RetryConfig | None) -> "QueryDeps":
        """Build QueryDeps from current state."""
        from src.agent.query.deps import QueryDeps
        from src.context.micro import micro_compact
        from src.context.compact import auto_compact

        async def async_autocompact(
            messages: list[Message],
            llm_client,
        ) -> "AutoCompactResult | None":
            return await auto_compact(
                messages=messages,
                count_tokens=self._client.count_tokens,
                llm_client=llm_client,
                resolve_limit=lambda: self._ctx_limit,
                tracking=None,
                ratio=self._config.context_ratio,
            )

        return QueryDeps(
            call_model=self._client.chat,
            count_tokens=self._client.count_tokens,
            get_tool_schemas=lambda: self._executor.to_schemas(),
            get_tools=lambda: {t.name: t for t in self._executor.tools},
            execute_tool=self._executor.execute,
            microcompact=micro_compact,
            autocompact=async_autocompact,
            llm_client=self._client,
            resolve_limit=lambda: self._ctx_limit,
            retry_config=retry_config,
            agent_name=self._config.name,
        )

    # ── Convenience run ───────────────────────────────────────────────────

    async def run(self, user_input: str) -> str:
        """Run agent on user input. Returns final text response.

        Convenience wrapper around run_stream() that discards all events
        except the final text.
        """
        final_text = ""
        async for event in self.run_stream(user_input):
            if isinstance(event, TextEvent) and event.type == "content":
                final_text += event.text
        return final_text
