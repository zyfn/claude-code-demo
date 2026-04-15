"""TodoWrite tool — model manages a session task checklist.

Delegates to TodoManager for validation and state mutation.
Returns fixed text — model already knows what it wrote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from src.tools.types import ToolResult

if TYPE_CHECKING:
    from src.planning import TodoManager

DESCRIPTION = (
    "Update the todo list for the current session. Use proactively for "
    "multi-step tasks (3+ steps). Each item needs: content (imperative: "
    "'Run tests'), status (pending/in_progress/completed), active_form "
    "(present continuous: 'Running tests'). Rules: exactly ONE task "
    "in_progress at a time, mark completed IMMEDIATELY after finishing, "
    "remove irrelevant tasks entirely."
)

_PARAMS = {
    "todos": {
        "type": "array",
        "description": "The complete updated todo list.",
        "items": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Imperative: 'Run tests'"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                "active_form": {"type": "string", "description": "Present continuous: 'Running tests'"},
            },
            "required": ["content", "status", "active_form"],
        },
    },
}


@dataclass
class TodoWriteTool:
    name: str = "todo_write"
    description: str = DESCRIPTION
    parameters: dict = field(default_factory=lambda: dict(_PARAMS))
    _manager: Any = field(default=None, repr=False)  # TodoManager

    async def execute(self, todos: list[dict] | None = None, **_: Any) -> ToolResult:
        if todos is None:
            return ToolResult("Missing required parameter: todos", is_error=True)
        if self._manager is None:
            return ToolResult("TodoWriteTool not configured", is_error=True)
        try:
            self._manager.update(todos)
        except ValueError as e:
            return ToolResult(str(e), is_error=True)
        return ToolResult("Todos updated. Proceed with current tasks.")

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return True
