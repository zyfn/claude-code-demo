"""System prompt builder — separates static role/guidelines from dynamic tool/skill lists.

Claude Code's prompt organization:
- Role + guidelines: static, baked into template
- Tool descriptions: from tool.prompt() — dynamic
- Skill descriptions: from skill loader — dynamic, versioned
- CLAUDE.md: user message injection, not system prompt

This module handles building the "static" portion of the system prompt
(tools + skills names/descriptions). The actual content is rebuilt each
session; the component parts (tool descriptions, skill descriptions)
come from live registries.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.base import BaseTool


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


# Fallback tool descriptions when tool.prompt() is not available.
TOOL_DESCRIPTIONS = {
    "bash": "Execute a shell command. Returns stdout and stderr.",
    "read_file": "Read the contents of a file.",
    "write_file": "Create or overwrite a file with content.",
    "edit_file": "Make precise edits to a file by replacing exact text.",
    "grep": "Search for patterns in files using grep.",
    "glob": "Find files matching a glob pattern.",
    "delegate": "Delegate a sub-task to a specialized agent.",
    "load_skill": "Load the full content of a skill by name.",
}


def get_tool_description(tool: "BaseTool") -> str:
    """Get tool description, preferring the tool's own prompt() method."""
    # Tool.prompt(options) is the Claude Code pattern for dynamic descriptions.
    # Fall back to tool.description or TOOL_DESCRIPTIONS.
    desc = getattr(tool, "prompt", None)
    if desc:
        try:
            import inspect
            sig = inspect.signature(desc)
            if len(sig.parameters) >= 1:
                # tool.prompt(options) — pass empty options
                return desc({})
            return desc()
        except Exception:
            pass
    return TOOL_DESCRIPTIONS.get(tool.name, tool.description)


def build_system_prompt(tools: list["BaseTool"], skills_str: str) -> str:
    """Build system prompt with current tools and skills.

    Args:
        tools: List of enabled tool instances
        skills_str: Formatted skill descriptions (from SkillLoader.get_descriptions())
    """
    tool_lines = []
    for t in tools:
        if t.is_enabled():
            desc = get_tool_description(t)
            tool_lines.append(f"- {t.name}: {desc}")
    tools_str = "\n".join(tool_lines) if tool_lines else "(no tools available)"

    return SYSTEM_PROMPT_TEMPLATE.format(
        tools=tools_str,
        skills=skills_str if skills_str else "(no skills available)",
    )


def load_claude_md(root: str) -> str | None:
    """Load CLAUDE.md from project root or any parent directory.

    Searches up the directory tree, starting from root, returning the first
    CLAUDE.md found. This matches Claude Code's behaviour where CLAUDE.md
    files in parent directories also apply.
    """
    path = Path(root).resolve()
    for parent in [path] + list(path.parents):
        md_path = parent / "CLAUDE.md"
        if md_path.is_file():
            return md_path.read_text(encoding="utf-8")
    return None
