"""UI abstraction — protocol and null implementation."""

from typing import Protocol


class UIHandler(Protocol):
    """Protocol for UI handlers.

    The TUI implements this with direct event methods (on_content, on_reasoning, etc.)
    rather than a single on_event dispatch. This file also provides NullUI for
    headless/programmatic use.
    """

    def print_banner(self) -> None:
        ...

    def prompt_input(self) -> str:
        ...

    def spinner(self):
        """Context manager for the thinking spinner."""
        ...

    def flush(self) -> None:
        ...
