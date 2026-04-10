"""LLM client using LiteLLM — returns raw stream."""

from __future__ import annotations

import json
from collections.abc import AsyncIterable
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Protocol, Optional, cast, TYPE_CHECKING

import litellm
from litellm.types.utils import Message, StreamingChatCompletionChunk

if TYPE_CHECKING:
    pass  # Protocol doesn't need runtime import


class LLMClientProtocol(Protocol):
    """Protocol for LLM clients — allows dependency injection."""

    def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamingChatCompletionChunk, None]:
        ...

    def count_tokens(self, messages: list[Message], tools: Optional[list[dict]] = None) -> int:
        ...


def get_model_info(model: str) -> dict[str, Any]:
    """Get model metadata from LiteLLM's built-in cost table."""
    try:
        return cast(dict[str, Any], litellm.get_model_info(model))
    except Exception:
        return {}


class LLMClient(LLMClientProtocol):
    """Simple LLM client using LiteLLM — returns raw async generator."""

    def __init__(self, model: str, api_key: str, api_base: str | None = None, debug_log: bool = False):
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._debug_log = debug_log
        self._log_dir: Path | None = None
        if debug_log:
            self._log_dir = Path("debug")
            self._log_dir.mkdir(exist_ok=True)

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[StreamingChatCompletionChunk, None]:
        """Return raw async generator of streaming chunks."""
        kwargs: dict = {
            "model": self._model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "max_tokens": max_tokens,
            "stream": True,
            "api_key": self._api_key,
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if tools:
            kwargs["tools"] = tools

        chunks_log: list[StreamingChatCompletionChunk] = []

        stream = await litellm.acompletion(**kwargs)
        async for chunk in cast(AsyncIterable[StreamingChatCompletionChunk], stream):
            chunks_log.append(chunk)
            yield chunk

        # Save debug log after stream completes
        if self._log_dir:
            self._save_debug(self._log_dir, kwargs, chunks_log)

    def _save_debug(
        self, out_dir: Path, request: dict, chunks: list[StreamingChatCompletionChunk]
    ) -> None:
        """Save debug log: raw chunks + reconstructed data."""
        # Reconstruct from chunks
        text = ""
        tool_calls_raw: list[dict] = []
        reasoning = ""
        stop_reason = "stop"
        usage = None

        for chunk in chunks:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning += rc
            if delta.content:
                text += delta.content
            for tc in getattr(delta, "tool_calls", None) or []:
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

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (out_dir / f"call_{ts}.json").write_text(
            json.dumps({
                "request": request,
                "chunks_count": len(chunks),
                "reconstructed": {
                    "text": text,
                    "reasoning": reasoning,
                    "tool_calls": tool_calls_raw,
                    "stop_reason": stop_reason,
                }
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def count_tokens(self, messages: list[Message], tools: list[dict] | None = None) -> int:
        return litellm.token_counter(
            model=self._model,
            messages=[m.model_dump(exclude_none=True) for m in messages],
            tools=cast(Any, tools),
        )
