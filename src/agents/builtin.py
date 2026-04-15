"""Built-in agent definitions."""

from src.agents.types import AgentDefinition

GENERAL_PURPOSE_AGENT = AgentDefinition(
    agent_type="general-purpose",
    when_to_use=(
        "General-purpose agent for researching complex questions, searching code, "
        "and executing multi-step tasks. Use when a task requires exploring many "
        "files or performing independent work that shouldn't pollute the main conversation."
    ),
    system_prompt=(
        "You are a sub-agent for a coding assistant. Complete the given task fully "
        "using the tools available. Be thorough but concise.\n\n"
        "Guidelines:\n"
        "- Search broadly when you don't know where something lives\n"
        "- Be thorough: check multiple locations, consider different naming conventions\n"
        "- When done, respond with a concise summary of findings and actions taken"
    ),
    tools=None,  # all tools
    max_turns=15,
)

EXPLORE_AGENT = AgentDefinition(
    agent_type="explore",
    when_to_use=(
        "Read-only agent for exploring codebases, searching for patterns, "
        "and answering questions about code structure. Cannot modify files."
    ),
    system_prompt=(
        "You are a read-only exploration agent. Your job is to search and analyze "
        "code to answer questions. You CANNOT modify any files.\n\n"
        "Guidelines:\n"
        "- Use grep and read_file to explore the codebase\n"
        "- Provide a clear, structured summary of your findings"
    ),
    tools=["read_file", "grep"],
    max_turns=30,
)


def get_builtin_agents() -> list[AgentDefinition]:
    return [GENERAL_PURPOSE_AGENT, EXPLORE_AGENT]
