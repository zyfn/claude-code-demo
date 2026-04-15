"""AgentTool — spawns a sub-agent with isolated context.

Design (aligned with Claude Code):
  - Sub-agent has its own messages + executor
  - Shares parent's abort_signal (sync agent = linked cancellation)
  - Shares parent's can_use_tool (permission inheritance)
  - Forwards ToolEvent to parent (UI shows sub-agent's tool progress)
  - Returns sub-agent's final text as tool_result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from src.tools.types import Tool, ToolResult

DESCRIPTION = (
    "Spawn a sub-agent to handle a task independently. The sub-agent has its own "
    "conversation context and returns a summary when done."
)

_PARAMS = {
    "prompt": {"type": "string", "description": "Task for the sub-agent."},
    "description": {"type": "string", "description": "Short description (shown to user)."},
    "subagent_type": {"type": "string", "description": "Agent type to spawn.", "optional": True},
}


@dataclass
class SubAgentTool:
    name: str = "subagent"
    description: str = DESCRIPTION
    parameters: dict = field(default_factory=lambda: dict(_PARAMS))

    # Injected by registry
    _agent_defs: list = field(default_factory=list, repr=False)
    _core_tools: list = field(default_factory=list, repr=False)
    _client: Any = field(default=None, repr=False)
    _hooks: Any = field(default=None, repr=False)
    _can_use_tool: Any = field(default=None, repr=False)
    _compaction_stages: list = field(default_factory=list, repr=False)
    _abort_signal: Any = field(default=None, repr=False)
    _on_event: Any = field(default=None, repr=False)  # Callable[[Event], None] — forward sub-agent events to UI

    def __post_init__(self):
        if self._agent_defs:
            lines = "\n".join(f"  - {a.agent_type}: {a.when_to_use}" for a in self._agent_defs)
            self.description = f"{DESCRIPTION}\n\nAvailable types:\n{lines}"

    async def execute(self, prompt: str = "", description: str = "", subagent_type: str = "", **_: Any) -> ToolResult:
        if not prompt:
            return ToolResult("Missing required parameter: prompt", is_error=True)
        if not self._client:
            return ToolResult("AgentTool not configured", is_error=True)

        agent_def = self._resolve(subagent_type)
        if not agent_def:
            available = ", ".join(a.agent_type for a in self._agent_defs)
            return ToolResult(f"Unknown agent type: '{subagent_type}'. Available: {available}", is_error=True)

        final_text = ""
        reason = ""
        async for event in self._run(prompt, agent_def):
            if self._on_event:
                self._on_event(event)
            from src.types import QueryComplete
            if isinstance(event, QueryComplete):
                final_text = event.text
                reason = event.reason
                break

        if not final_text:
            return ToolResult(f"Sub-agent ended without output (reason: {reason})", is_error=True)

        return ToolResult(final_text or "Sub-agent completed with no output.")

    def is_enabled(self) -> bool:
        return self._client is not None

    def is_read_only(self) -> bool:
        return True

    def _resolve(self, subagent_type: str):
        if not subagent_type and self._agent_defs:
            return self._agent_defs[0]
        for d in self._agent_defs:
            if d.agent_type == subagent_type:
                return d
        return None

    async def _run(self, prompt: str, agent_def) -> AsyncGenerator[Event, None]:
        """Core: build QueryDeps, call query(), yield all events."""
        from litellm.types.utils import Message
        from src.query import query
        from src.tools.executor import ToolExecutor
        from src.types import QueryDeps

        # Filter tools per agent definition
        if agent_def.tools is not None:
            allowed = set(agent_def.tools)
            tool_map = {t.name: t for t in self._core_tools if t.name in allowed}
        else:
            tool_map = {t.name: t for t in self._core_tools}

        # Share parent's abort_signal (sync agent — Ctrl+C cancels both)
        abort = self._abort_signal

        deps = QueryDeps(
            client=self._client,
            tool_executor=ToolExecutor(
                tools=tool_map, hooks=self._hooks,
                can_use_tool=self._can_use_tool, abort_signal=abort,
            ),
            hooks=self._hooks, abort_signal=abort,
            compaction_stages=self._compaction_stages,
        )

        async for event in query(
            messages=[Message(role="user", content=prompt)],
            system_prompt=agent_def.system_prompt,
            system_context={}, user_context={},
            deps=deps, max_turns=agent_def.max_turns,
        ):
            yield event
