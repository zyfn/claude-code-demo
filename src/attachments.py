"""Per-turn attachment injection — checked every turn inside query().

Stateless: scans messages to decide what to inject.
New attachment sources go here, not in repl.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from litellm.types.utils import Message

from src.planning import needs_todo_reminder, build_todo_reminder

if TYPE_CHECKING:
    from src.planning import TodoManager


def get_attachments(messages: list[Message], todo: TodoManager) -> list[Message]:
    """Collect all per-turn attachments. Called by query via QueryDeps."""
    result: list[Message] = []
    if needs_todo_reminder(messages, todo):
        result.append(Message(role="user", content=build_todo_reminder(todo)))
    # Future: add more attachment sources here
    return result
