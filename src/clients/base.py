"""Base LLM client interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_result: dict | None = None


@dataclass
class ToolCall:
    name: str
    parameters: dict
    id: str = ""


@dataclass
class AssistantResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class BaseClient(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
    ) -> AssistantResponse:
        ...
