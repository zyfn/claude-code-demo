"""LLM client — thin wrapper around LiteLLM with optional debug logging."""

from __future__ import annotations

import json
from collections.abc import AsyncIterable
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Protocol, cast

import litellm
from litellm.types.utils import Message, StreamingChatCompletionChunk


class LLMClient(Protocol):
    """Protocol for LLM clients — enables test injection."""

    async def stream(
        self, messages: list[Message], tools: list[dict] | None = None, max_tokens: int | None = None,
    ) -> AsyncGenerator[StreamingChatCompletionChunk, None]: ...

    def count_tokens(self, messages: list[Message], tools: list[dict] | None = None) -> int: ...

    def get_context_limit(self) -> int: ...


class LiteLLMClient:
    """Production LLM client with optional debug logging.

    When debug_dir is set, each API call is logged to a JSON file containing:
    - request: model, messages, tools, max_tokens
    - response: reconstructed text, tool_calls, reasoning, stop_reason
    - metadata: timestamp, chunk count
    """

    def __init__(self, model: str, api_key: str, api_base: str | None = None, debug_dir: Path | None = None):
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._debug_dir = debug_dir
        self._call_seq = 0  # auto-incrementing call sequence number
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)

    async def stream(
        self, messages: list[Message], tools: list[dict] | None = None, max_tokens: int | None = None,
    ) -> AsyncGenerator[StreamingChatCompletionChunk, None]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "stream": True, "api_key": self._api_key,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if tools:
            kwargs["tools"] = tools

        chunks: list[StreamingChatCompletionChunk] = []
        raw = await litellm.acompletion(**kwargs)
        async for chunk in cast(AsyncIterable[StreamingChatCompletionChunk], raw):
            if self._debug_dir:
                chunks.append(chunk)
            yield chunk

        if self._debug_dir:
            self._save_debug(kwargs, chunks)

    def count_tokens(self, messages: list[Message], tools: list[dict] | None = None) -> int:
        return litellm.token_counter(
            model=self._model, messages=[m.model_dump(exclude_none=True) for m in messages], tools=cast(Any, tools),
        )

    def get_context_limit(self) -> int:
        try:
            return litellm.get_model_info(self._model).get("max_input_tokens", 128_000)
        except Exception:
            return 128_000

    def _save_debug(self, request: dict, chunks: list[StreamingChatCompletionChunk]) -> None:
        """Reconstruct the full response from chunks and save to debug/."""
        self._call_seq += 1

        text = ""
        reasoning = ""
        tool_calls: list[dict] = []
        stop_reason = ""
        usage: dict[str, int] | None = None

        for chunk in chunks:
            # Extract usage from the final chunk (OpenAI/Anthropic put it there)
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage:
                usage = {
                    "prompt_tokens": getattr(chunk_usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(chunk_usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(chunk_usage, "total_tokens", 0) or 0,
                }

            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta.content:
                text += delta.content
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning += rc
            for tc in getattr(delta, "tool_calls", None) or []:
                idx = tc.index
                while len(tool_calls) <= idx:
                    tool_calls.append({"id": "", "name": "", "arguments": ""})
                entry = tool_calls[idx]
                if tc.id:
                    entry["id"] = tc.id
                fn = tc.function
                if fn:
                    if fn.name:
                        entry["name"] += fn.name
                    if fn.arguments:
                        entry["arguments"] += fn.arguments
            if choice.finish_reason:
                stop_reason = choice.finish_reason

        safe_request = {k: v for k, v in request.items() if k != "api_key"}

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self._debug_dir / f"call_{ts}.json"
        path.write_text(json.dumps({
            "timestamp": ts,
            "call_sequence": self._call_seq,
            "request": safe_request,
            "response": {
                "text": text,
                "reasoning": reasoning,
                "tool_calls": tool_calls,
                "stop_reason": stop_reason,
                "usage": usage,
            },
            "chunks_count": len(chunks),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
