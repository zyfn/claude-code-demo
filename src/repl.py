"""Interactive REPL — holds messages, assembles deps, calls query()."""

import httpx
from pathlib import Path
from litellm.types.utils import Message

from src.config import Config
from src.context import get_system_context, get_user_context
from src.hooks import HookRegistry
from src.planning import TodoManager
from src.attachments import get_attachments
from src.system_prompt import SYSTEM_PROMPT
from src.types import (
    CompactionEvent, ContentDelta, QueryComplete, QueryDeps,
    ReasoningDelta, ToolEvent, ToolsReady, TurnStart, Event,
)
from src.query import query
from src.api.client import LiteLLMClient
from src.compact.budget import budget_stage
from src.compact.micro import micro_stage
from src.compact.auto import auto_stage
from src.tools import get_all_tools
from src.tools.types import ToolCall, ToolResult
from src.tools.executor import ToolExecutor
from src.tools.execution import AbortSignal
from src.agents.builtin import get_builtin_agents
from src.ui import TUI


def _make_event_handler(tui: TUI):
    def handle(event: Event) -> list[Message] | None:
        if isinstance(event, TurnStart):
            tui.on_turn(event.turn)
        elif isinstance(event, ContentDelta):
            tui.on_content(event.text)
        elif isinstance(event, ReasoningDelta):
            tui.on_reasoning(event.text)
        elif isinstance(event, ToolEvent):
            tui.on_tool(event)
        elif isinstance(event, ToolsReady):
            tui.flush_live()
        elif isinstance(event, CompactionEvent):
            tui.on_compaction(event.stage, event.deleted_count)
        elif isinstance(event, QueryComplete):
            tui.on_final(event.reason)
            return event.messages if event.messages else None
        return None
    return handle


async def repl_loop(config: Config) -> None:
    config.validate_startup()
    tui = TUI()
    tui.banner()

    client = LiteLLMClient(
        model=config.effective_model,
        api_key=config.effective_api_key,
        api_base=config.effective_api_base,
        debug_dir=Path("debug") if config.debug_log else None,
    )
    stages = [budget_stage, micro_stage, auto_stage]

    hooks = HookRegistry()
    hooks_file = Path(config.project_root) / ".ccc" / "hooks.yaml"
    loaded = hooks.load_from_file(hooks_file)
    if loaded > 0:
        tui.console.print(f"[dim]Loaded {loaded} hook(s) from {hooks_file}[/dim]")

    async def can_use_tool(call: ToolCall) -> ToolResult | None:
        if tui.confirm_tool(call.name, call.params):
            return None
        return ToolResult(f"Tool '{call.name}' was denied by user.", is_error=True)

    # Session state
    todo = TodoManager()
    agent_defs = get_builtin_agents()
    handle_event = _make_event_handler(tui)
    messages: list[Message] = []
    abort_signal: AbortSignal | None = None

    while True:
        try:
            user_input = tui.prompt()
            if not user_input.strip():
                continue
            if user_input.strip().lower() in ("quit", "exit", "/quit", "/exit"):
                tui.console.print("[yellow]Goodbye![/]")
                break

            abort_signal = AbortSignal()

            tools = get_all_tools(
                todo_manager=todo, agent_defs=agent_defs,
                client=client, hooks=hooks,
                can_use_tool=can_use_tool, compaction_stages=stages,
                abort_signal=abort_signal,
                on_agent_event=handle_event,
            )
            tool_map = {t.name: t for t in tools}

            system_context = get_system_context(config.project_root)
            user_context = get_user_context(config.project_root)

            turn_messages = [*messages, Message(role="user", content=user_input)]

            deps = QueryDeps(
                client=client,
                tool_executor=ToolExecutor(
                    tools=tool_map, hooks=hooks,
                    can_use_tool=can_use_tool, abort_signal=abort_signal,
                ),
                hooks=hooks, abort_signal=abort_signal,
                compaction_stages=stages,
                get_attachments=lambda msgs: get_attachments(msgs, todo),
            )

            async for event in query(
                messages=turn_messages,
                system_prompt=SYSTEM_PROMPT,
                system_context=system_context,
                user_context=user_context,
                deps=deps,
                max_output_tokens=config.max_tokens,
            ):
                result = handle_event(event)
                if result is not None:
                    messages = list(result)

        except KeyboardInterrupt:
            if abort_signal:
                abort_signal.abort()
            tui.console.print("\n[yellow]Interrupted. Type /quit to exit.[/]")
        except EOFError:
            tui.console.print("\n[yellow]Goodbye![/]")
            break
        except httpx.TimeoutException:
            tui.on_error("Request timed out")
        except httpx.HTTPStatusError as e:
            tui.on_error(f"API error {e.response.status_code}: {e.response.text[:200]}")
        except httpx.RequestError as e:
            tui.on_error(f"Network error: {e}")
        except Exception as e:
            tui.on_error(f"{type(e).__name__}: {e}")
