"""High-level Agent API and loop exports.

This module re-exports the public API:
- agent_loop() from core.py
- Agent class (simplified, no EventBus)
- StreamEvent types from types.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncGenerator

from litellm.types.utils import Message

from src.agent.core import agent_loop as _agent_loop, LoopConfig
from src.agent.deps import AgentDeps
from src.agent.types import StreamEvent, TextEvent, ToolStartEvent, ToolResultEvent, FinalEvent
from src.agent.retry import RetryConfig
from src.tools.executor import ToolExecutor
from src.llm.client import get_model_info

if TYPE_CHECKING:
    from src.llm.client import LLMClientProtocol
    from src.tools.base import BaseTool


# ─── Public re-exports ─────────────────────────────────────────────────────────

agent_loop = _agent_loop
__all__ = ["Agent", "AgentConfig", "agent_loop", "StreamEvent"]


# ─── Agent Config ──────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """Configuration for the high-level Agent API."""
    name: str = "agent"
    system_prompt: str = ""
    max_iterations: int = 20
    max_tokens: int = 8192
    context_ratio: float = 0.8


# ─── High-level Agent ──────────────────────────────────────────────────────────

class Agent:
    """High-level Agent API — wires loop + executor + context manager.

    Simplest usage:
        agent = Agent(config, client, tools)
        async for event in agent.run_stream(user_input):
            if isinstance(event, TextEvent):
                print(event.text, end="", flush=True)

    For direct loop access (no buffering):
        deps = agent.make_deps()
        async for event in agent_loop(config, deps, agent._messages):
            ...
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
        self._messages: list[Message] = [Message(role="system", content=config.system_prompt)]

        primary_model = getattr(client, "_model", "")
        ctx_limit = get_model_info(primary_model).get("max_input_tokens", 128_000)

        from src.context.messages import ContextManager
        self._ctx = ContextManager(
            messages=self._messages,
            count_tokens=client.count_tokens,
            resolve_limit=lambda: ctx_limit,
            ratio=config.context_ratio,
        )

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

    # ── Deps factory ───────────────────────────────────────────────────────

    def make_deps(
        self,
        retry_config: RetryConfig | None = None,
    ) -> AgentDeps:
        """Build AgentDeps from current state.

        Call this after adding/removing tools if you need fresh schemas.
        """
        return AgentDeps(
            call_model=self._client.chat,
            count_tokens=self._client.count_tokens,
            get_tool_schemas=lambda: self._executor.to_schemas(),
            get_tools=lambda: {t.name: t for t in self._executor.tools},
            execute_tool=self._executor.execute,
            apply_context_compactions=lambda tools, llm_client: self._ctx.apply_compactions(tools, llm_client),
            retry_config=retry_config,
            llm_client=self._client,
            agent_name=self._config.name,
        )

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

        loop_config = LoopConfig(
            name=self._config.name,
            max_iterations=self._config.max_iterations,
            max_tokens=self._config.max_tokens,
        )

        deps = self.make_deps(retry_config=retry_config)

        async for event in _agent_loop(loop_config, deps, self._messages):
            yield event

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
