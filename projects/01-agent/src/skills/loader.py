"""Skill loader — loads skills from SKILL.md files (两层注入设计).

Layer 1: format_skills_for_system_prompt() → 系统提示中的简短描述
Layer 2: get_skill_content(name) → 模型调用 load_skill 时返回完整内容
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .types import ToolUseContext


FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class ParsedSkill:
    """A skill parsed from a SKILL.md file."""
    name: str
    description: str
    content: str  # Markdown content after frontmatter
    metadata: dict  # Raw metadata from frontmatter
    root_dir: str
    user_invocable: bool = False
    disable_model_invocation: bool = False
    allowed_tools: list[str] = field(default_factory=list)
    when_to_use: str = ""


@dataclass
class SkillLoader:
    """Skill loader with 两层注入 design.

    Layer 1: get_descriptions() → 系统提示中的简短描述
    Layer 2: get_content(name) → tool_result 中的完整内容
    """

    _skills: dict[str, ParsedSkill] = field(default_factory=dict)
    # Tracks skills activated via /skill command to avoid duplicate injection
    # when the model also calls load_skill. Cleared on agent reset.
    _active_skills: set[str] = field(default_factory=set)

    def mark_active(self, name: str) -> None:
        """Mark a skill as active (called by main.py /skill command)."""
        self._active_skills.add(name)

    def is_active(self, name: str) -> bool:
        """Check if a skill was already activated via /skill."""
        return name in self._active_skills

    def reset_active(self) -> None:
        """Clear active skill registry. Call when starting a new conversation."""
        self._active_skills.clear()

    def load_from_dir(self, skills_dir: str) -> None:
        """Load all SKILL.md files from a directory.

        Skills are subdirectories containing SKILL.md.
        """
        skills_path = Path(skills_dir)
        if not skills_path.is_dir():
            return

        for entry in skills_path.iterdir():
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.is_file():
                continue

            parsed = self._load_skill_file(skill_file, entry)
            if parsed:
                self._skills[parsed.name] = parsed

    def _load_skill_file(self, skill_path: Path, skill_dir: Path) -> ParsedSkill | None:
        """Load a single SKILL.md file."""
        content = skill_path.read_text(encoding="utf-8")
        meta, body = self._parse_frontmatter(content)

        name = meta.get("name", skill_dir.name)
        description = meta.get("description", "")
        user_invocable = meta.get("user_invocable", False)
        disable_model_invocation = meta.get("disable_model_invocation", False)
        allowed_tools = meta.get("allowed_tools", [])
        when_to_use = meta.get("when_to_use", "")

        return ParsedSkill(
            name=name,
            description=description,
            content=body.strip(),
            metadata=meta,
            root_dir=str(skill_dir),
            user_invocable=user_invocable,
            disable_model_invocation=disable_model_invocation,
            allowed_tools=allowed_tools,
            when_to_use=when_to_use,
        )

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """Parse YAML frontmatter from skill markdown."""
        import yaml  # type: ignore
        match = FRONTMATTER_PATTERN.match(content)
        if not match:
            return {}, content
        metadata = yaml.safe_load(match.group(1)) or {}
        body = content[match.end():]
        return metadata, body

    def get_descriptions(self) -> str:
        """Layer 1: 返回系统提示中的技能名称和描述（不含 header）。"""
        if not self._skills:
            return ""

        lines = []
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            if not skill.description:
                continue
            line = f"- **{skill.name}**: {skill.description}"
            if skill.when_to_use:
                line += f" ({skill.when_to_use})"
            lines.append(line)

        return "\n".join(lines)

    def get_content(self, name: str) -> str | None:
        """Layer 2: 返回完整技能内容（用于 tool_result）。"""
        skill = self._skills.get(name)
        if not skill:
            return None
        return f"<skill name=\"{skill.name}\">\n{skill.content}\n</skill>"

    def get(self, name: str) -> ParsedSkill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def get_all(self) -> list[ParsedSkill]:
        """Get all loaded skills."""
        return list(self._skills.values())

    def get_user_invocable(self) -> list[ParsedSkill]:
        """Get skills that can be invoked via /command."""
        return [s for s in self._skills.values() if s.user_invocable]


# Global singleton
_skill_loader: SkillLoader | None = None


def get_skill_loader() -> SkillLoader:
    """Get the global SkillLoader instance."""
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
        _init_bundled_skills(_skill_loader)
        _load_user_skills(_skill_loader)
    return _skill_loader


def _init_bundled_skills(loader: SkillLoader) -> None:
    """Load bundled skills from the bundled/ directory."""
    bundled_dir = os.path.join(os.path.dirname(__file__), "bundled")
    loader.load_from_dir(bundled_dir)


def _load_user_skills(loader: SkillLoader) -> None:
    """Load user skills from ~/.openclaw/skills/."""
    user_skills_dir = os.path.expanduser("~/.openclaw/skills")
    loader.load_from_dir(user_skills_dir)


def format_skills_for_system_prompt() -> str:
    """Format skills list for injection into system prompt (Layer 1)."""
    return get_skill_loader().get_descriptions()


def get_skill_content(name: str) -> str | None:
    """Get full skill content (Layer 2)."""
    return get_skill_loader().get_content(name)
