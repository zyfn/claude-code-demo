"""Terminal UI — Rich Live for dynamic tool status.

Tool display uses Rich Live (non-transient):
  - running: adds ⏳ to Live, in-place refresh
  - completed/error: updates ⏳→✓/✗ in-place
  - finalize: stops Live, final state stays on screen

flush_live() forces synchronous render — called between submit and drain
to guarantee ⏳ is painted before execution starts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from src.types import ToolEvent

STATUS_ICON = {
    "running": ("⏳", "yellow"),
    "completed": ("✓", "green"),
    "error": ("✗", "red"),
    "rejected": ("✗", "red"),
}


class TUI:
    def __init__(self):
        self.console = Console()
        self._reasoning_buf = ""
        self._content_buf = ""
        self._tool_states: list[tuple[str, str, str]] = []  # (status, desc, tool_call_id)
        self._live: Live | None = None

    def banner(self) -> None:
        self.console.print(Panel("[bold cyan]CCC[/] — AI Coding Assistant v0.2", style="cyan"))

    def prompt(self) -> str:
        return self.console.input("\n[bold green]You → [/]")

    def on_turn(self, turn: int) -> None:
        self._finalize_tools()

    def on_reasoning(self, text: str) -> None:
        self._finalize_tools()
        self._flush_content()
        self._reasoning_buf += text
        if "\n" in self._reasoning_buf:
            lines = self._reasoning_buf.split("\n")
            self._reasoning_buf = lines[-1]
            for line in lines[:-1]:
                if line:
                    self.console.print(f"[dim]◌ {line}[/dim]")

    def on_content(self, text: str) -> None:
        self._finalize_tools()
        self._flush_reasoning()
        self._content_buf += text
        if "\n" in self._content_buf:
            lines = self._content_buf.split("\n")
            self._content_buf = lines[-1]
            for line in lines[:-1]:
                self.console.print(line)

    def on_tool(self, event: "ToolEvent") -> None:
        desc = _desc(event.name, event.params)
        tid = event.tool_call_id

        if event.status == "running":
            self._flush_reasoning()
            self._flush_content()
            self._tool_states.append(("running", desc, tid))
            self._refresh_live()

        elif event.status in ("completed", "error"):
            for i, (s, d, t) in enumerate(self._tool_states):
                if t == tid:
                    self._tool_states[i] = (event.status, desc, tid)
                    self._refresh_live()
                    return
            self._tool_states.append((event.status, desc, tid))
            self._refresh_live()

        elif event.status == "rejected":
            self._flush_reasoning()
            self._flush_content()
            self._pause_live()
            icon, color = STATUS_ICON["rejected"]
            self.console.print(f"  [{color}]{icon}[/] {desc}")

    def confirm_tool(self, name: str, params: dict) -> bool:
        self._flush_reasoning()
        self._flush_content()
        self._pause_live()
        desc = _desc(name, params)
        answer = self.console.input(f"  [yellow]⚠ {desc}[/] Allow? [y/N] ").strip().lower()
        return answer in ("y", "yes")

    def flush_live(self) -> None:
        """Force synchronous render of Live display."""
        if self._live is not None:
            self._live.refresh()

    def on_compaction(self, stage: str, deleted_count: int) -> None:
        self._finalize_tools()
        self.console.print(
            f"[dim]⟳ Context compacted ({stage}): {deleted_count} messages removed[/dim]"
        )

    def on_final(self, reason: str) -> None:
        self._finalize_tools()
        self._flush_reasoning()
        self._flush_content()

    def on_error(self, msg: str) -> None:
        self._finalize_tools()
        self._flush_reasoning()
        self._flush_content()
        self.console.print(f"[red]Error: {msg}[/]")

    def flush(self) -> None:
        self._flush_reasoning()
        self._flush_content()

    # ── Internal ──────────────────────────────────────────────────────

    def _flush_reasoning(self) -> None:
        if self._reasoning_buf:
            self._pause_live()
            self.console.print(f"[dim]◌ {self._reasoning_buf}[/dim]")
            self._reasoning_buf = ""

    def _flush_content(self) -> None:
        if self._content_buf:
            self._pause_live()
            self.console.print(self._content_buf)
            self._content_buf = ""

    def _refresh_live(self) -> None:
        display = self._build_display()
        if self._live is None:
            self._live = Live(
                display, console=self.console,
                refresh_per_second=10, transient=False,
            )
            self._live.start()
        else:
            self._live.update(display)

    def _build_display(self) -> Group:
        texts = []
        for status, desc, _ in self._tool_states:
            icon, color = STATUS_ICON.get(status, ("?", "white"))
            texts.append(Text.from_markup(f"  [{color}]{icon}[/] {desc}"))
        return Group(*texts)

    def _pause_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _finalize_tools(self) -> None:
        if self._live is not None:
            self._live.update(self._build_display())
            self._live.stop()
            self._live = None
        self._tool_states.clear()


def _desc(name: str, params: dict) -> str:
    parts = [f"{k}={repr(v)[:50]}" for k, v in params.items()]
    return f"{name}({', '.join(parts)})"
