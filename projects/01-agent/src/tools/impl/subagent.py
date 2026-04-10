"""SubAgent tool — delegate a task to a child agent.

This tool allows an agent to spawn a sub-agent to handle a specialized
subtask, with isolated context and tools.
"""

from typing import TYPE_CHECKING

from src.tools.base import BaseTool
from src.tools.executor import ToolResult
from litellm.types.utils import Message

if TYPE_CHECKING:
    from src.agent.loop import Agent


class SubAgentTool(BaseTool):
    """Delegate a task to a child agent (sub-agent pattern)."""

    name = "delegate"
    description = "Delegate a sub-task to a specialized agent. Use for complex tasks requiring focused context."
    parameters = {
        "task": {"type": "string", "description": "The task description for the sub-agent"},
        "agent_type": {
            "type": "string",
            "description": "Type of sub-agent to use (e.g., 'coder', 'reviewer', 'researcher')",
            "optional": True,
        },
    }
    max_result_size_chars = 100_000  # Sub-agents can return more

    def is_read_only(self, **kwargs) -> bool:
        return True

    def is_concurrency_safe(self, **kwargs) -> bool:
        return True

    async def execute(self, task: str, agent_type: str | None = None, **kwargs) -> ToolResult:
        """Execute a sub-agent to handle the task."""
        from src.agent.loop import Agent, AgentConfig
        from src.agent.types import TextEvent

        client = kwargs.get("_sub_agent_client")
        if client is None:
            return ToolResult("Error: No LLM client configured for sub-agent", is_error=True)

        system_prompt = kwargs.get("_sub_agent_system_prompt", "")
        max_tokens = kwargs.get("_sub_agent_max_tokens", 4096)

        config = AgentConfig(
            name=f"subagent_{agent_type or 'default'}",
            system_prompt=system_prompt,
            max_iterations=10,
            max_tokens=max_tokens,
        )

        from src.tools import get_all_tools
        tools = get_all_tools()

        agent = Agent(config=config, client=client, tools=tools)

        final_text = ""
        try:
            async for event in agent.run_stream(task):
                if isinstance(event, TextEvent) and event.type == "content":
                    final_text += event.text
        except Exception as e:
            return ToolResult(f"Sub-agent error: {e}", is_error=True)

        return ToolResult(final_text)


async def spawn_sub_agent(
    task: str,
    agent_type: str | None,
    client,
    tools: list[BaseTool],
    system_prompt: str = "",
    max_iterations: int = 10,
    max_tokens: int = 4096,
) -> str:
    """Spawn a sub-agent and return its final response."""
    from src.agent.loop import Agent, AgentConfig
    from src.agent.types import TextEvent

    config = AgentConfig(
        name=f"subagent_{agent_type or 'default'}",
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
    )

    agent = Agent(config=config, client=client, tools=tools)

    final_text = ""
    try:
        async for event in agent.run_stream(task):
            if isinstance(event, TextEvent) and event.type == "content":
                final_text += event.text
    except Exception as e:
        return f"Error: {e}"

    return final_text
