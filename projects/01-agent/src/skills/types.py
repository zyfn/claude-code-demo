"""Skill system types — unified Command abstraction for all skill sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.tools.base import BaseTool


class SkillSource(Enum):
    """Where the skill was loaded from."""
    BUNDLED = "bundled"
    SKILLS_DIR = "skills"
    PLUGIN = "plugin"
    MCP = "mcp"
    MANAGED = "managed"


class ExecutionContext(Enum):
    """How the skill executes."""
    INLINE = "inline"  # Expand into current conversation
    FORK = "fork"  # Run in a separate sub-agent


@dataclass
class SkillConfig:
    """Configuration for a skill's behavior."""
    name: str
    description: str
    aliases: list[str] = field(default_factory=list)
    when_to_use: str | None = None
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    is_enabled: bool = True
    source: SkillSource = SkillSource.BUNDLED
    context: ExecutionContext = ExecutionContext.INLINE
    agent: str | None = None
    hooks: dict | None = None
    skill_root: str | None = None
    files: dict[str, str] | None = None  # name -> content


@dataclass
class ToolUseContext:
    """Context passed when a skill is invoked."""
    cwd: str = "."
    session_id: str = ""
    user_id: str | None = None
    tool_permission_context: dict | None = None

    def get_app_state(self) -> dict:
        return {}


class Command(ABC):
    """Base class for all commands (skills)."""

    config: SkillConfig

    @abstractmethod
    async def get_prompt(self, args: str, context: ToolUseContext) -> str:
        """Generate the full prompt for this skill.

        Args:
            args: The arguments passed to the skill
            context: The tool use context

        Returns:
            The full prompt content (markdown)
        """
        ...

    def is_available(self) -> bool:
        """Check if this skill is currently available."""
        return self.config.is_enabled


class InlineCommand(Command):
    """A skill that executes inline (expands into current conversation)."""

    async def get_prompt(self, args: str, context: ToolUseContext) -> str:
        raise NotImplementedError


class ForkCommand(Command):
    """A skill that executes in a forked sub-agent."""

    def __init__(self, config: SkillConfig, agent_type: str = "general-purpose"):
        self.config = config
        self.config.context = ExecutionContext.FORK
        self.config.agent = agent_type

    async def get_prompt(self, args: str, context: ToolUseContext) -> str:
        raise NotImplementedError
