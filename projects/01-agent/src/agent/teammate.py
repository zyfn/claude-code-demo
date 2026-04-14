"""In-process teammate system using AsyncLocalStorage for isolation.

Implements the InProcessBackend pattern from Claude Code:
- Each teammate runs with AsyncLocalStorage for context isolation
- Mailbox-based communication between teammates
- Independent agent loops per teammate
"""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

from src.agent.mailbox import MailboxMessage, TeammateMailbox


# Context variable for teammate isolation (task-local storage)
_current_teammate: ContextVar["TeammateContext | None"] = ContextVar(
    "teammate", default=None
)


def get_current_teammate() -> "TeammateContext | None":
    """Get the current teammate context (None if not in a teammate)."""
    try:
        return _current_teammate.get()
    except LookupError:
        return None


@dataclass
class TeammateConfig:
    """Configuration for a teammate."""
    id: str
    team: str
    prompt: str
    tools: list[Any]  # List of BaseTool
    system_prompt: str = ""
    model: str = "claude-sonnet-4-6"
    max_turns: int = 20
    max_output_tokens: int = 8192


@dataclass
class TeammateContext:
    """Context for a running teammate — stored in AsyncLocalStorage."""
    agent_id: str
    team_name: str
    mailbox: TeammateMailbox
    main_mailbox: Optional["TeammateMailbox"] = None
    metadata: dict = field(default_factory=dict)


async def run_teammate(
    config: TeammateConfig,
    client: "LLMClientProtocol",
    main_mailbox: Optional[TeammateMailbox] = None,
) -> None:
    """Run a teammate agent in an isolated context.

    Uses AsyncLocalStorage so each teammate has its own context.
    Communicates with coordinator via mailbox.
    """
    from src.agent import Agent, AgentConfig
    from src.agent.query.types import FinalEvent

    mailbox = TeammateMailbox(config.id, config.team)
    ctx = TeammateContext(
        agent_id=config.id,
        team_name=config.team,
        mailbox=mailbox,
        main_mailbox=main_mailbox,
    )

    # Run in isolated AsyncLocalStorage context
    _current_teammate.set(ctx)

    try:
        agent_config = AgentConfig(
            name=config.id,
            system_prompt=config.system_prompt,
            max_turns=config.max_turns,
            max_output_tokens=config.max_output_tokens,
        )

        agent = Agent(config=agent_config, client=client, tools=config.tools)

        final_event = None
        async for event in agent.run_stream(config.prompt):
            if isinstance(event, FinalEvent):
                final_event = event

        # Notify main mailbox of completion
        if main_mailbox:
            result_reason = final_event.reason if final_event else "no_response"
            main_mailbox.send(MailboxMessage(
                source=config.id,
                content=f"Task completed: {result_reason}",
                metadata={"status": "done"},
            ))
    finally:
        _current_teammate.set(None)


async def spawn_in_process_teammates(
    configs: list[TeammateConfig],
    client: "LLMClientProtocol",
    coordinator_mailbox: TeammateMailbox,
) -> list[asyncio.Task]:
    """Spawn multiple teammates in the same process.

    Each teammate runs in its own AsyncLocalStorage context for isolation.
    Returns list of tasks for the spawned teammates.
    """
    tasks: list[asyncio.Task] = []

    for config in configs:
        task = asyncio.create_task(
            run_teammate(config, client, coordinator_mailbox)
        )
        tasks.append(task)

    return tasks


async def wait_for_teammates(
    tasks: list[asyncio.Task],
    timeout: Optional[float] = None,
) -> list[Any]:
    """Wait for all teammates to complete. Returns results or raises TimeoutError."""
    if timeout:
        return await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
    return await asyncio.gather(*tasks, return_exceptions=True)
