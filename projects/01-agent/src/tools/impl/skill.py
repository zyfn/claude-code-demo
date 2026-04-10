"""LoadSkillTool — 按需加载技能完整内容 (Layer 2).

当模型需要使用某个技能时，调用 load_skill("skill_name", args="...")。
返回完整技能内容到 tool_result，注入到对话中。

两层注入设计:
- Layer 1: 系统提示中只有技能名称/描述（SkillLoader.get_descriptions）
- Layer 2: 模型调用 load_skill 时返回完整内容
"""

from __future__ import annotations

from src.tools.base import BaseTool
from src.tools.executor import ToolResult
from src.skills import get_skill_loader


class LoadSkillTool(BaseTool):
    """Tool for loading skill content on demand (两层注入 Layer 2).

    模型在系统提示中看到技能名称列表（Layer 1），
    当需要使用某个技能时，调用此工具获取完整内容（Layer 2）。
    """

    name = "load_skill"
    description = "Load the full content of a skill by name. Use when you need to use a specific skill."
    parameters = {
        "skill": {
            "type": "string",
            "description": "The name of the skill to load (e.g., 'ask', 'simplify')",
        },
        "args": {
            "type": "string",
            "description": "Optional arguments to pass to the skill",
            "optional": True,
        },
    }

    async def execute(self, skill: str, args: str = "", **kwargs) -> ToolResult:
        """Load skill content and return it for injection into the conversation."""
        skill_name = skill.strip()
        loader = get_skill_loader()

        # Get skill
        parsed = loader.get(skill_name)
        if not parsed:
            available = ", ".join(s.name for s in loader.get_all())
            return ToolResult(
                f"Unknown skill: {skill_name}. Available skills: {available}",
                is_error=True,
            )

        # If already activated via /skill command, return lightweight notice.
        # The content was already injected by main.py; avoid duplication.
        if loader.is_active(skill_name):
            return ToolResult(
                f"[Skill '{skill_name}' is already active. Content was injected via /skill command.]",
            )

        # Get content and substitute variables
        content = parsed.content
        content = content.replace("${CLAUDE_SKILL_DIR}", parsed.root_dir)
        content = content.replace("${ARGUMENTS}", args or "")

        # Append user args if provided (only when model calls directly, not via /skill)
        if args:
            content += f"\n\n## User Request\n\n{args}"

        # Return wrapped in skill tag for clear injection
        wrapped = f"<skill name=\"{skill_name}\">\n{content}\n</skill>"
        return ToolResult(wrapped)

    def is_enabled(self) -> bool:
        """Check if there are any skills available."""
        return len(get_skill_loader().get_all()) > 0
