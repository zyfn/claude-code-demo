"""Agent hook system — registration-based, not inheritance-based.

Design inspired by OpenAI Agents tracing + Claude Code hooks + Google ADK events.

Usage:
    agent = AgentLoop(client, tools)
    agent.on("tool_use", lambda name, params: print(f"🔧 {name}"))
    agent.on("stream_chunk", lambda chunk: print(chunk, end=""))
    result = await agent.run("hello")

Events:
    think(text)         — LLM produced reasoning/thinking content
    tool_use(name, params) — A tool is about to be executed
    tool_result(output, is_error) — Tool execution completed
    stream_start()      — Streaming output beginning
    stream_chunk(chunk) — A chunk of streamed text
    stream_end()        — Streaming output finished
    done(text)          — Final response ready
    error(exc)          — An error occurred
"""

from typing import Any, Callable


Hook = Callable[..., Any]


class HookRegistry:
    """Stores named hooks and dispatches events to registered handlers."""

    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {}

    def on(self, name: str, handler: Hook) -> None:
        """Register a handler for a named event."""
        self._hooks.setdefault(name, []).append(handler)

    def emit(self, name: str, **kwargs: Any) -> None:
        """Fire an event, calling all registered handlers."""
        for handler in self._hooks.get(name, []):
            handler(**kwargs)
