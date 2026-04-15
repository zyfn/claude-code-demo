"""Public types shared across modules.

Events, compaction interfaces, QueryDeps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Union

from litellm.types.utils import Message


# ━━ Events ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass(slots=True)
class TurnStart:
    turn: int


@dataclass(slots=True)
class ContentDelta:
    text: str


@dataclass(slots=True)
class ReasoningDelta:
    text: str


@dataclass(slots=True)
class ToolEvent:
    """Unified tool event — one type, different statuses."""
    name: str
    params: dict
    tool_call_id: str
    status: str  # "running" | "completed" | "error" | "rejected"
    output: str = ""


@dataclass(slots=True)
class CompactionEvent:
    stage: str
    deleted_count: int


@dataclass(slots=True)
class ToolsReady:
    """All tools submitted (⏳ yielded). Execution about to start.

    UI should force-render to ensure ⏳ is visible before drain.
    """
    count: int


@dataclass
class QueryComplete:
    """Final event. Carries authoritative messages snapshot."""
    reason: str
    messages: list[Message] = field(default_factory=list)
    text: str = ""
    error: str | None = None
    turn_count: int = 0


Event = Union[
    TurnStart, ContentDelta, ReasoningDelta,
    ToolEvent, CompactionEvent, ToolsReady, QueryComplete,
]


# ━━ Compaction interfaces ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class CompactionContext:
    messages: list[Message]
    token_count: int
    context_limit: int
    client: Any
    compaction_tracking: Any


@dataclass(slots=True)
class CompactionResult:
    messages: list[Message]
    deleted_count: int
    tracking: Any = None
    stage_name: str = ""


CompactionStage = Callable[[CompactionContext], Awaitable[CompactionResult]]


# ━━ QueryDeps ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class QueryDeps:
    client: Any                # LLMClient Protocol
    tool_executor: Any         # ToolExecutor (has hooks + can_use_tool inside)
    hooks: Any                 # HookRegistry — query uses for Stop, future PreLLMCall etc.
    abort_signal: Any          # AbortSignal — shared by query + executor
    compaction_stages: list[CompactionStage] = field(default_factory=list)
    get_attachments: Callable[[list[Message]], list[Message]] | None = None  # per-turn context injection

    @property
    def tool_schemas(self) -> list[dict]:
        return self.tool_executor.tool_schemas

    @property
    def context_limit(self) -> int:
        return self.client.get_context_limit()
