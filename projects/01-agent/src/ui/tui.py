"""Terminal UI using Rich — streaming output driven by direct events.

No EventBus — the TUI exposes event handler methods that are called
directly by the main loop. This follows Claude Code's architecture
where events flow directly from the query loop to the UI.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.ui.base import UIHandler


class TUI(UIHandler):
    """Simple terminal UI with clean streaming output.

    Event handlers are called directly by the main loop.
    No EventBus subscription needed.
    """

    def __init__(self):
        self.console = Console()
        self._reasoning_buf = ""
        self._content_buf = ""

    # ── Banner & input ───────────────────────────────────────────────────────

    def print_banner(self) -> None:
        banner = """
 ██████╗██╗      ██████╗ ██╗   ██╗██████╗ ███████╗██████╗
██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗██╔════╝██╔══██╗
██║     ██║     ██║   ██║██║   ██║██████╔╝█████╗  ██████╔╝
██║     ██║     ██║   ██║██║   ██║██╔══██╗██╔══╝  ██╔══██╗
╚██████╗███████╗╚██████╔╝╚██████╔╝██║  ██║███████╗██║  ██║
 ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
        Code Clone — AI Coding Assistant v0.1.0
"""
        self.console.print(Panel(banner, style="bold cyan"))

    def prompt_input(self) -> str:
        return self.console.input("\n[bold green]You → [/]")

    def spinner(self):
        """Context manager that flushes buffers when the spinner exits."""
        class SpinnerCtx:
            def __enter__(ctx):
                return status.__enter__()
            def __exit__(ctx, *args):
                self.flush()
                return status.__exit__(*args)
        status = self.console.status("[bold cyan]Thinking...")
        return SpinnerCtx()

    # ── Event handlers (called directly by main loop) ───────────────────────

    def on_turn_start(self, turn: int) -> None:
        """Start of a new agent turn."""
        pass

    def on_reasoning(self, text: str) -> None:
        """Streaming reasoning/thinking fragment."""
        self._flush_content()
        self._reasoning_buf += text
        if '\n' in self._reasoning_buf:
            lines = self._reasoning_buf.split('\n')
            self._reasoning_buf = lines[-1]
            for line in lines[:-1]:
                if line:
                    self.console.print(f"[dim]◌ {line}[/dim]")

    def on_content(self, chunk: str) -> None:
        """Streaming text content fragment."""
        self._flush_reasoning()
        self._content_buf += chunk
        if '\n' in self._content_buf:
            lines = self._content_buf.split('\n')
            self._content_buf = lines[-1]
            for line in lines[:-1]:
                self.console.print(line)

    def on_tool_start(self, name: str, params: dict) -> None:
        """A tool call is about to execute."""
        self._flush_reasoning()
        self._flush_content()

        parts = []
        for k, v in params.items():
            if isinstance(v, str) and len(v) > 50:
                v = f'"{v[:47]}..."'
            parts.append(f"[dim]{k}[/]=[cyan]{repr(v)[:50]}[/]")

        param_str = ", ".join(parts)
        self.console.print(f"[yellow]▶[/] [bold blue]{name}[/]  [white]([/]{param_str}[white])[/]")

    def on_tool_result(self, name: str, is_error: bool) -> None:
        """Tool execution completed."""
        icon = "[red]✗[/]" if is_error else "[green]✓[/]"
        self.console.print(f"  {icon}")

    def on_final(self, reason: str) -> None:
        """Agent completed with a final response."""
        self.flush()

    def on_error(self, message: str) -> None:
        """Non-recoverable error occurred."""
        self._flush_reasoning()
        self._flush_content()
        self.console.print(f"[red]Error: {message}[/red]")

    # ── Internal ─────────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Flush any pending output (reasoning + content buffers)."""
        self._flush_reasoning()
        self._flush_content()

    def _flush_reasoning(self) -> None:
        if self._reasoning_buf:
            self.console.print(f"[dim]◌ {self._reasoning_buf}[/dim]")
            self._reasoning_buf = ""

    def _flush_content(self) -> None:
        if self._content_buf:
            self.console.print(self._content_buf)
            self._content_buf = ""
