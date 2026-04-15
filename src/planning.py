"""Planning — session-level task checklist.

PlanningState is pure data. TodoManager owns validation, rendering.
Reminder logic is stateless — scans messages to decide, no counters.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.constants import PLAN_REMINDER_INTERVAL, PLAN_MAX_ITEMS


@dataclass
class PlanItem:
    content: str
    status: str = "pending"
    active_form: str = ""


@dataclass
class PlanningState:
    items: list[PlanItem] = field(default_factory=list)


class TodoManager:
    def __init__(self) -> None:
        self.state = PlanningState()

    def update(self, items: list[dict]) -> str:
        """Validate and replace the plan. Returns rendered text."""
        if len(items) > PLAN_MAX_ITEMS:
            raise ValueError(f"Keep the session plan short (max {PLAN_MAX_ITEMS} items)")

        normalized: list[PlanItem] = []
        in_progress_count = 0

        for i, raw in enumerate(items):
            content = str(raw.get("content", "")).strip()
            status = str(raw.get("status", "pending")).lower()
            active_form = str(raw.get("active_form", raw.get("activeForm", ""))).strip()

            if not content:
                raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1

            normalized.append(PlanItem(content=content, status=status, active_form=active_form))

        if in_progress_count > 1:
            raise ValueError("Only one plan item can be in_progress")

        if normalized and all(p.status == "completed" for p in normalized):
            normalized = []

        self.state.items = normalized
        return self.render()

    def get_active_form(self) -> str | None:
        for item in self.state.items:
            if item.status == "in_progress":
                return item.active_form or None
        return None

    def render(self) -> str:
        if not self.state.items:
            return "No session plan yet."
        lines = []
        for item in self.state.items:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item.status]
            line = f"{marker} {item.content}"
            if item.status == "in_progress" and item.active_form:
                line += f"  ({item.active_form})"
            lines.append(line)
        completed = sum(1 for p in self.state.items if p.status == "completed")
        lines.append(f"\n({completed}/{len(self.state.items)} completed)")
        return "\n".join(lines)


def needs_todo_reminder(messages: list, todo: TodoManager) -> bool:
    """Scan messages to decide if a todo reminder is needed. Stateless.

    Triggers only when:
      1. There is an active plan (items non-empty)
      2. Model HAS used todo_write before (found in messages)
      3. Enough turns have passed since last todo_write
      4. Enough turns have passed since last reminder (no spam)
    """
    if not todo.state.items:
        return False

    turns_since_write = 0
    turns_since_reminder = 0
    found_write = False
    found_reminder = False

    for msg in reversed(messages):
        role = getattr(msg, "role", None)

        if role == "assistant":
            if not found_write:
                turns_since_write += 1
            if not found_reminder:
                turns_since_reminder += 1

            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                name = getattr(fn, "name", "") if fn else ""
                if name == "todo_write":
                    found_write = True
                    break

        if role == "user":
            content = getattr(msg, "content", "") or ""
            if isinstance(content, str) and "<todo_reminder>" in content:
                found_reminder = True

        if found_write and found_reminder:
            break

    # Only remind if model has used todo_write before but stopped updating
    if not found_write:
        return False

    return (
        turns_since_write >= PLAN_REMINDER_INTERVAL
        and turns_since_reminder >= PLAN_REMINDER_INTERVAL
    )


def build_todo_reminder(todo: TodoManager) -> str:
    """Build reminder text to inject as a user message."""
    return (
        "<todo_reminder>You haven't updated your plan recently. "
        "Review and refresh it before continuing.</todo_reminder>\n\n"
        + todo.render()
    )
