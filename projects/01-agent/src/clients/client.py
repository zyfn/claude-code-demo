"""LLM client using LiteLLM — unified interface for all providers."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

import litellm

from src.config import settings


@dataclass
class Message:
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_calls: list["ToolCall"] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class ToolCall:
    name: str
    parameters: dict
    id: str = ""


@dataclass
class AssistantResponse:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "stop"


def _model_name() -> str:
    if settings.provider == "openai":
        return f"openai/{settings.openai_model}"
    return f"anthropic/{settings.model}"


def _api_key() -> str:
    if settings.provider == "openai":
        return settings.openai_api_key
    return settings.api_key


def _api_base() -> str | None:
    if settings.provider == "openai":
        return settings.openai_api_base or None
    return settings.api_base or None


class LLMClient:
    def __init__(self):
        self._log_dir = None
        if settings.debug_log:
            self._log_dir = Path("debug")
            self._log_dir.mkdir(exist_ok=True)

    def _save_debug(self, payload: dict, response_data: dict):
        if not self._log_dir:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (self._log_dir / f"call_{ts}.json").write_text(
            json.dumps({"request": payload, "response": response_data}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_messages(self, messages: list[Message]) -> list[dict]:
        chat_messages = []
        for m in messages:
            msg: dict = {"role": m.role}
            if m.role == "tool":
                msg["tool_call_id"] = m.tool_call_id
                msg["content"] = m.content
            elif m.role == "assistant" and m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.parameters)},
                    }
                    for tc in m.tool_calls
                ]
                if m.content:
                    msg["content"] = m.content
            else:
                msg["content"] = m.content
            chat_messages.append(msg)
        return chat_messages

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
        on_chunk: Callable[[str], None] | None = None,
    ) -> AssistantResponse:
        chat_messages = self._build_messages(messages)
        stream = on_chunk is not None

        kwargs: dict = {
            "model": _model_name(),
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "stream": stream,
            "api_key": _api_key(),
        }
        base = _api_base()
        if base:
            kwargs["base_url"] = base
        if tools:
            kwargs["tools"] = tools

        if stream:
            return await self._do_stream(kwargs, on_chunk)
        else:
            resp = await litellm.acompletion(**kwargs)
            choice = resp.choices[0]
            msg = choice.message
            self._save_debug(kwargs, resp.model_dump())
            return AssistantResponse(
                text=msg.content or "",
                reasoning=msg.reasoning_content or "",
                tool_calls=[
                    ToolCall(
                        name=tc.function.name,
                        parameters=json.loads(tc.function.arguments),
                        id=tc.id or "",
                    )
                    for tc in (msg.tool_calls or [])
                ],
                stop_reason=choice.finish_reason or "stop",
            )

    async def _do_stream(
        self,
        kwargs: dict,
        on_chunk: Callable[[str], None],
    ) -> AssistantResponse:
        text = ""
        reasoning = ""
        tool_calls_raw: list[dict] = []
        stop_reason = "stop"

        stream = await litellm.acompletion(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning += rc

            if delta.content:
                text += delta.content
                on_chunk(delta.content)

            for tc in delta.tool_calls or []:
                idx = tc.index
                fn = tc.function
                if idx >= len(tool_calls_raw):
                    tool_calls_raw.append({"id": "", "name": "", "arguments": ""})
                entry = tool_calls_raw[idx]
                if tc.id:
                    entry["id"] = tc.id
                if fn and fn.name:
                    entry["name"] += fn.name
                if fn and fn.arguments:
                    entry["arguments"] += fn.arguments

            if choice.finish_reason:
                stop_reason = choice.finish_reason

        self._save_debug(kwargs, {"text": text, "reasoning": reasoning, "tool_calls": tool_calls_raw})
        return AssistantResponse(
            text=text,
            reasoning=reasoning,
            tool_calls=[
                ToolCall(name=tc["name"], parameters=json.loads(tc["arguments"] or "{}"), id=tc["id"])
                for tc in tool_calls_raw if tc["name"]
            ],
            stop_reason=stop_reason,
        )
