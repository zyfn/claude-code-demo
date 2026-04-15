"""Agent definition — describes a sub-agent type."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    """Describes a sub-agent type that AgentTool can spawn."""
    agent_type: str           # e.g. "general-purpose", "explore"
    when_to_use: str          # description for the model
    system_prompt: str        # sub-agent's system prompt
    tools: list[str] | None = None  # None = all tools, ["read_file"] = restricted
    max_turns: int = 10
