"""Main entry point — wires together all components.

Architecture: agent_loop yields StreamEvents directly to TUI (no EventBus).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import httpx

from litellm.types.utils import Message

from src.config import settings
from src.llm.client import LLMClient
from src.agent.loop import Agent, AgentConfig
from src.agent.types import TextEvent, ToolStartEvent, ToolResultEvent, FinalEvent, TurnStart
from src.agent.retry import RetryConfig
from src.tools import get_all_tools
from src.ui.tui import TUI
from src.context.system import ProjectContext
from src.skills import format_skills_for_system_prompt, get_skill_loader


# Initialize skill loader (loads bundled + user skills from .md files)
skill_loader = get_skill_loader()
skill_loader.reset_active()  # Clear any stale active skills from prior sessions


# ─── System prompt builder ──────────────────────────────────────────────────────

TOOL_DESCRIPTIONS = {
    "Read": "Read the contents of a file.",
    "Write": "Create or overwrite a file with content.",
    "Edit": "Make precise edits to a file by replacing exact text.",
    "Bash": "Execute a shell command.",
    "Grep": "Search for patterns in files using grep.",
    "Glob": "Find files matching a glob pattern.",
    "delegate": "Delegate a sub-task to a specialized agent.",
    "load_skill": "Load the full content of a skill by name.",
}


SYSTEM_PROMPT_TEMPLATE = """You are an expert AI coding assistant.

## Available Tools
{tools}

## Available Skills
{skills}

## Guidelines
1. Explore the codebase before making changes — use Read, Grep, Glob to understand the structure
2. Make incremental changes, verify each step
3. Run tests to confirm correctness
4. Keep changes focused and minimal
5. If a task requires a specific skill, use the /skill command or load_skill tool
"""


def build_system_prompt() -> str:
    """Build the system prompt with role, tools, and skills."""
    tools = get_all_tools()
    tool_lines = []
    for t in tools:
        if t.is_enabled():
            desc = TOOL_DESCRIPTIONS.get(t.name, t.description)
            tool_lines.append(f"- {t.name}: {desc}")
    tools_str = "\n".join(tool_lines) if tool_lines else "(no tools available)"

    skills_str = format_skills_for_system_prompt()

    return SYSTEM_PROMPT_TEMPLATE.format(
        tools=tools_str,
        skills=skills_str if skills_str else "(no skills available)",
    )


def load_claude_md(root: str) -> str | None:
    """Load CLAUDE.md from project root or any parent directory (like Claude Code).

    Searches up the directory tree, starting from root, returning the first
    CLAUDE.md found. This matches Claude Code's behavior where CLAUDE.md files
    in parent directories also apply.
    """
    path = Path(root).resolve()
    for parent in [path] + list(path.parents):
        md_path = parent / "CLAUDE.md"
        if md_path.is_file():
            return md_path.read_text(encoding="utf-8")
    return None


def create_agent() -> Agent:
    """Composition root: assemble all components."""
    model = f"{settings.provider}/{settings.model}" if settings.provider == "anthropic" else f"openai/{settings.openai_model}"
    client = LLMClient(
        model=model,
        api_key=settings.effective_api_key,
        api_base=settings.effective_api_base,
        debug_log=settings.debug_log,
    )

    tools = get_all_tools()
    system_prompt = build_system_prompt()

    agent = Agent(
        config=AgentConfig(
            name="main",
            system_prompt=system_prompt,
            max_tokens=settings.max_tokens,
        ),
        client=client,
        tools=tools,
    )
    return agent


async def run_tui_events(tui: TUI, agent: Agent, user_input: str) -> str:
    """Run agent and forward events directly to TUI."""
    final_text = ""
    retry_config = RetryConfig()

    async for event in agent.run_stream(user_input, retry_config):
        if isinstance(event, TurnStart):
            tui.on_turn_start(event.turn)
        elif isinstance(event, TextEvent):
            if event.type == "content":
                tui.on_content(event.text)
                final_text += event.text
            elif event.type == "reasoning":
                tui.on_reasoning(event.text)
        elif isinstance(event, ToolStartEvent):
            tui.on_tool_start(event.name, event.params)
        elif isinstance(event, ToolResultEvent):
            tui.on_tool_result(event.name, event.is_error)
        elif isinstance(event, FinalEvent):
            tui.on_final(event.reason)

    return final_text


async def main_loop():
    agent = create_agent()
    tui = TUI()
    tui.print_banner()

    ctx = ProjectContext(settings.project_root)
    tui.console.print(ctx.get_context_summary())

    # Inject CLAUDE.md as user message at session start (same as Claude Code)
    claude_md = load_claude_md(settings.project_root)
    if claude_md:
        agent.inject_messages([Message(role="user", content=f"## CLAUDE.md\n\n{claude_md}")])

    while True:
        try:
            user_input = tui.prompt_input()
            if not user_input.strip():
                continue
            if user_input.lower() in ("quit", "exit", "/quit"):
                tui.console.print("[yellow]Goodbye![/]")
                break

            # Slash command: /skill args
            if user_input.startswith("/"):
                parts = user_input[1:].split(None, 1)
                skill_name = parts[0]
                skill_args = parts[1] if len(parts) > 1 else ""

                loader = get_skill_loader()
                skill = loader.get(skill_name)
                if skill:
                    # Mark active BEFORE injecting so subsequent load_skill calls
                    # (if model calls them) return lightweight notice instead of
                    # duplicating the content.
                    loader.mark_active(skill_name)

                    # Build skill content message — same substitution as load_skill
                    content = skill.content
                    content = content.replace("${CLAUDE_SKILL_DIR}", skill.root_dir)
                    content = content.replace("${ARGUMENTS}", skill_args)
                    if skill_args:
                        content += f"\n\n## User Request\n\n{skill_args}"

                    wrapped = (
                        f'<skill name="{skill_name}">\n'
                        f"{content}\n"
                        f"</skill>"
                    )
                    agent.inject_messages([Message(role="user", content=wrapped)])
                    with tui.spinner():
                        await run_tui_events(tui, agent, "")
                    continue
                else:
                    tui.console.print(f"[yellow]Unknown skill: {skill_name}[/]")
                    continue

            with tui.spinner():
                await run_tui_events(tui, agent, user_input)

        except KeyboardInterrupt:
            tui.console.print("\n[yellow]Interrupted. Type /quit to exit.[/]")
        except EOFError:
            tui.console.print("\n[yellow]Goodbye![/]")
            break
        except httpx.TimeoutException:
            tui.console.print("[red]Error: Request timed out.[/]")
        except httpx.HTTPStatusError as e:
            tui.console.print(f"[red]API error {e.response.status_code}: {e.response.text[:200]}[/]")
        except httpx.RequestError as e:
            tui.console.print(f"[red]Network error: {e}[/]")
        except Exception as e:
            tui.console.print(f"[red]Unexpected error: {type(e).__name__}: {e}[/]")


def main():
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()
