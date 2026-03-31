"""Terminal UI using Rich."""

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live


class TUI:
    def __init__(self):
        self.console = Console()
        self._status = None
        self._live = None
        self._stream_buffer = ""
        self._streamed = False
        self._pending_tool = ""

    # ── Banner & prompts ──────────────────────────────────────────

    def print_banner(self):
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

    def print_response(self, text: str):
        self.console.print(Panel(
            Markdown(text),
            title="🦞 Claw",
            border_style="cyan",
        ))

    # ── Spinner ───────────────────────────────────────────────────

    def start_spinner(self):
        self._status = self.console.status("[bold cyan]Thinking...", spinner="dots")
        self._status.__enter__()
        self._streamed = False

    def stop_spinner(self):
        if self._status:
            self._status.__exit__(None, None, None)
            self._status = None

    # ── Hook handlers ─────────────────────────────────────────────

    def on_think(self, text: str) -> None:
        self.stop_spinner()
        self.console.print(Panel(
            Markdown(text[:500] + "..." if len(text) > 500 else text),
            title="🤔 Thinking",
            border_style="yellow",
        ))

    def on_tool_use(self, name: str, params: dict) -> None:
        self.stop_spinner()
        param_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in params.items())
        self._pending_tool = f" 🔧 [bold blue]{name}[/]({param_str})"

    def on_tool_result(self, output: str, is_error: bool) -> None:
        icon = "❌" if is_error else "  ✅"
        label = self._pending_tool
        self.console.print(f"{icon} {label}")

    def on_stream_start(self) -> None:
        self.stop_spinner()
        self._stream_buffer = ""
        self._live = Live(
            Panel("", title="🦞 Claw", border_style="cyan"),
            console=self.console,
            refresh_per_second=10,
        )
        self._live.__enter__()

    def on_stream_chunk(self, chunk: str) -> None:
        self._stream_buffer += chunk
        self._live.update(
            Panel(Markdown(self._stream_buffer), title="🦞 Claw", border_style="cyan")
        )

    def on_stream_end(self) -> None:
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None
            self._streamed = True

    def on_stream_reset(self) -> None:
        self._streamed = False
        self._stream_buffer = ""
