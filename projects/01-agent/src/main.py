"""Main entry point."""

import asyncio
import httpx
from src.config import settings
from src.clients.client import LLMClient
from src.tools import file_tools  # noqa: F401 — triggers auto-registration
from src.tools.base import get_all_tools
from src.agent.loop import AgentLoop
from src.agent.callback import AgentCallback
from src.tui.interface import TUI
from src.context.project import ProjectContext


async def main_loop():
    tui = TUI()
    tui.print_banner()

    # Show project context
    ctx = ProjectContext(settings.project_root)
    tui.console.print(ctx.get_context_summary())

    client = LLMClient()
    tools = get_all_tools()
    agent = AgentLoop(client, tools)

    # Register TUI as hook handlers
    agent.on("think", tui.on_think)
    agent.on("tool_use", tui.on_tool_use)
    agent.on("tool_result", tui.on_tool_result)
    agent.on("stream_start", tui.on_stream_start)
    agent.on("stream_chunk", tui.on_stream_chunk)
    agent.on("stream_end", tui.on_stream_end)
    agent.on("stream_reset", tui.on_stream_reset)

    # Interactive loop
    while True:
        try:
            user_input = tui.prompt_input()
            if not user_input.strip():
                continue
            if user_input.lower() in ("quit", "exit", "/quit"):
                tui.console.print("[yellow]Goodbye! 👋[/]")
                break

            tui.start_spinner()
            result = await agent.run(user_input)
            tui.stop_spinner()

            # Don't re-print if streaming already showed the final response
            if not tui._streamed:
                tui.print_response(result)

        except KeyboardInterrupt:
            tui.stop_spinner()
            tui.console.print("\n[yellow]Interrupted. Type /quit to exit.[/]")
        except EOFError:
            tui.stop_spinner()
            tui.console.print("\n[yellow]Goodbye![/]")
            break
        except httpx.TimeoutException:
            tui.stop_spinner()
            tui.console.print("[red]Error: Request timed out. The model took too long to respond.[/]")
        except httpx.HTTPStatusError as e:
            tui.stop_spinner()
            tui.console.print(f"[red]API error {e.response.status_code}: {e.response.text[:200]}[/]")
        except httpx.RequestError as e:
            tui.stop_spinner()
            tui.console.print(f"[red]Network error: {e}[/]")
        except Exception as e:
            tui.stop_spinner()
            tui.console.print(f"[red]Unexpected error: {type(e).__name__}: {e}[/]")


def main():
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()
