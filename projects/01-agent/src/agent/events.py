"""Event system for agent lifecycle hooks.

Design: Event emitter pattern (not inheritance-based callbacks).

Why this over LangChain-style callbacks?
- No inheritance required — just register functions
- Add/remove handlers at runtime
- Multiple handlers per event
- Typed events with dataclasses
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    THINK = "think"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    STREAM_START = "stream_start"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    ERROR = "error"
    DONE = "done"


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)


# Type alias for event handlers
EventHandler = Callable[[Event], None]


class EventEmitter:
    """Minimal event emitter: register handlers, emit events."""

    def __init__(self):
        self._handlers: dict[EventType, list[EventHandler]] = {}

    def on(self, event: EventType, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: EventType, handler: EventHandler) -> None:
        """Remove a specific handler."""
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    def emit(self, event: Event) -> None:
        """Fire an event, calling all registered handlers."""
        for handler in self._handlers.get(event.type, []):
            handler(event)
