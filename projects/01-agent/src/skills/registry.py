"""Skill registry — manages bundled and loaded skills."""

from __future__ import annotations

from typing import Callable

from .types import Command, SkillConfig, SkillSource, ToolUseContext


# Global registry for all commands
_commands: dict[str, Command] = {}


def register_command(command: Command) -> None:
    """Register a command in the global registry."""
    _commands[command.config.name] = command
    # Also register aliases
    for alias in command.config.aliases:
        _commands[alias] = command


def get_command(name: str) -> Command | None:
    """Get a command by name."""
    return _commands.get(name)


def get_all_commands() -> list[Command]:
    """Get all registered commands."""
    return list(_commands.values())


def get_user_invocable_commands() -> list[Command]:
    """Get commands that can be invoked via /command."""
    return [cmd for cmd in _commands.values() if cmd.config.user_invocable]


def clear_commands() -> None:
    """Clear all registered commands (for testing)."""
    _commands.clear()


class BundledSkillRegistry:
    """Registry for bundled skills with lazy file extraction support."""

    _skills: dict[str, Command] = {}

    @classmethod
    def register(cls, config: SkillConfig, prompt_fn: Callable[[str, ToolUseContext], str]) -> None:
        """Register a bundled skill.

        Args:
            config: Skill configuration
            prompt_fn: Function that generates the prompt
        """
        cmd = _BundledCommand(config, prompt_fn)
        cls._skills[config.name] = cmd
        register_command(cmd)

        # Register aliases
        for alias in config.aliases:
            cls._skills[alias] = cmd
            _commands[alias] = cmd

    @classmethod
    def get(cls, name: str) -> Command | None:
        """Get a bundled skill by name."""
        return cls._skills.get(name)

    @classmethod
    def all(cls) -> list[Command]:
        """Get all bundled skills."""
        return list(cls._skills.values())

    @classmethod
    def clear(cls) -> None:
        """Clear all bundled skills (for testing)."""
        for name in list(cls._skills.keys()):
            cmd = cls._skills[name]
            if name in _commands:
                del _commands[name]
        cls._skills.clear()


class _BundledCommand(Command):
    """A bundled skill command with a prompt generation function."""

    def __init__(self, config: SkillConfig, prompt_fn: Callable[[str, ToolUseContext], str]):
        self.config = config
        self._prompt_fn = prompt_fn

    async def get_prompt(self, args: str, context: ToolUseContext) -> str:
        result = self._prompt_fn(args, context)
        if hasattr(result, "__await__"):
            return await result
        return result
