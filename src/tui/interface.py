"""Terminal UI using Rich."""

import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.layout import Layout
from rich.text import Text


class TUI:
    def __init__(self):
        self.console = Console()
        self.history: list[tuple[str, str]] = []  # (role, content)

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

    def print_thinking(self, text: str):
        self.console.print(Panel(
            Markdown(text[:500] + "..." if len(text) > 500 else text),
            title="🤔 Thinking",
            border_style="yellow",
        ))

    def print_tool_use(self, name: str, params: dict):
        param_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in params.items())
        self.console.print(f"  🔧 [bold blue]{name}[/]({param_str})")

    def print_tool_result(self, output: str, is_error: bool):
        preview = output[:300] + "..." if len(output) > 300 else output
        style = "red" if is_error else "green"
        icon = "❌" if is_error else "✅"
        self.console.print(Panel(
            preview,
            title=f"{icon} Tool Result",
            border_style=style,
        ))

    def print_response(self, text: str):
        self.console.print(Panel(
            Markdown(text),
            title="🦞 Claw",
            border_style="cyan",
        ))

    def prompt_input(self) -> str:
        return self.console.input("\n[bold green]You → [/]")

    def on_think(self, text: str):
        self.print_thinking(text)

    def on_tool_use(self, name: str, params: dict):
        self.print_tool_use(name, params)

    def on_result(self, output: str, is_error: bool):
        self.print_tool_result(output, is_error)
