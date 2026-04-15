"""Tool registry — assembles the tool pool."""

from __future__ import annotations

from typing import Any

from src.tools.types import Tool
from src.tools.impl.bash import BashTool
from src.tools.impl.file import ReadFileTool, WriteFileTool, EditFileTool
from src.tools.impl.grep import GrepTool
from src.tools.impl.todo import TodoWriteTool
from src.tools.impl.subagent import SubAgentTool


def get_core_tools() -> list[Tool]:
    return [BashTool(), ReadFileTool(), WriteFileTool(), EditFileTool(), GrepTool()]


def get_all_tools(
    todo_manager: Any = None,
    agent_defs: list | None = None,
    client: Any = None,
    hooks: Any = None,
    can_use_tool: Any = None,
    compaction_stages: list | None = None,
    abort_signal: Any = None,
    on_agent_event: Any = None,
) -> list[Tool]:
    """Full tool pool. Called each turn (abort_signal is per-turn)."""
    core = get_core_tools()
    tools: list[Tool] = list(core)
    tools.append(TodoWriteTool(_manager=todo_manager))
    if client and agent_defs:
        tools.append(SubAgentTool(
            _agent_defs=agent_defs, _core_tools=core,
            _client=client, _hooks=hooks,
            _can_use_tool=can_use_tool,
            _compaction_stages=compaction_stages or [],
            _abort_signal=abort_signal,
            _on_event=on_agent_event,
        ))
    return [t for t in tools if t.is_enabled()]
