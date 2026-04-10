"""Null UI — no output, for programmatic use."""

from src.ui.base import UIHandler


class NullUI(UIHandler):
    """A UI handler that does nothing — for testing or programmatic use."""

    def print_banner(self) -> None:
        pass

    def prompt_input(self) -> str:
        return ""

    def spinner(self):
        class _DummySpinner:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return _DummySpinner()

    def flush(self) -> None:
        pass

    def on_turn_start(self, turn: int) -> None:
        pass

    def on_reasoning(self, text: str) -> None:
        pass

    def on_content(self, chunk: str) -> None:
        pass

    def on_tool_start(self, name: str, params: dict) -> None:
        pass

    def on_tool_result(self, name: str, is_error: bool) -> None:
        pass

    def on_final(self, reason: str) -> None:
        pass

    def on_error(self, message: str) -> None:
        pass
