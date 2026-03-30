"""Main entry point."""

import asyncio
from src.config import settings
from src.clients.anthropic_client import AnthropicClient
from src.clients.openai_client import OpenAIClient
from src.tools.file_tools import ReadFileTool, WriteFileTool, EditFileTool, BashTool, GrepTool
from src.agent.loop import AgentLoop
from src.tui.interface import TUI
from src.context.project import ProjectContext


def create_client():
    if settings.provider == "openai":
        return OpenAIClient()
    return AnthropicClient()


async def main_loop():
    tui = TUI()
    tui.print_banner()

    # Show project context
    ctx = ProjectContext(settings.project_root)
    tui.console.print(ctx.get_context_summary())

    client = create_client()
    tools = [ReadFileTool(), WriteFileTool(), EditFileTool(), BashTool(), GrepTool()]
    agent = AgentLoop(client, tools)

    # Interactive loop
    while True:
        try:
            user_input = tui.prompt_input()
            if not user_input.strip():
                continue
            if user_input.lower() in ("quit", "exit", "/quit"):
                tui.console.print("[yellow]Goodbye! 👋[/]")
                break

            # Show spinner while thinking
            with tui.console.status("[bold cyan]Thinking...", spinner="dots"):
                result = await agent.run(
                    user_input,
                    on_think=tui.on_think,
                    on_tool_use=tui.on_tool_use,
                    on_result=tui.on_result,
                )

            tui.print_response(result)

        except KeyboardInterrupt:
            tui.console.print("\n[yellow]Interrupted. Type /quit to exit.[/]")
        except Exception as e:
            tui.console.print(f"[red]Error: {e}[/]")


def main():
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()
