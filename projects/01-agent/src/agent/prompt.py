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


def get_tool_description(tool: "BaseTool") -> str:
    """Get tool description from the tool instance.

    Claude Code pattern: tool.prompt(options) for dynamic descriptions.
    Fall back to static tool.description.
    """
    # Try tool.prompt(options) first — Claude Code's dynamic pattern
    prompt_method = getattr(tool, "prompt", None)
    if prompt_method:
        try:
            import inspect
            sig = inspect.signature(prompt_method)
            if len(sig.parameters) >= 1:
                return prompt_method({})
            return prompt_method()
        except Exception:
            pass
    # Fall back to static description
    return tool.description


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
