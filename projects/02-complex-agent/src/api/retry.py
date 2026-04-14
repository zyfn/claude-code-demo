"""Retry logic — network-level only (rate limit, timeout)."""

from __future__ import annotations

import asyncio
import random
from typing import AsyncGenerator

from litellm.types.utils import StreamingChatCompletionChunk

from src.api.client import LLMClient
from src.constants import RETRY_BASE_DELAY_MS, RETRY_MAX_BACKOFF_MS, RETRY_MAX_RETRIES


class ModelUnavailableError(Exception):
    pass


class PromptTooLongError(Exception):
    pass


def _classify(e: Exception) -> Exception:
    msg = str(e).lower()
    if any(k in msg for k in ("rate limit", "429", "too many requests")):
        return e
    if any(k in msg for k in ("prompt too long", "context_length", "maximum context")):
        return PromptTooLongError(str(e))
    if any(k in msg for k in ("model not found", "model unavailable", "404")):
        return ModelUnavailableError(str(e))
    return e


async def stream_with_retry(
    client: LLMClient, messages: list, tools: list[dict] | None,
    max_tokens: int | None = None, max_retries: int = RETRY_MAX_RETRIES,
) -> AsyncGenerator[StreamingChatCompletionChunk, None]:
    for attempt in range(1, max_retries + 2):
        try:
            async for chunk in client.stream(messages, tools, max_tokens):
                yield chunk
            return
        except (PromptTooLongError, ModelUnavailableError):
            raise
        except Exception as e:
            classified = _classify(e)
            if isinstance(classified, (PromptTooLongError, ModelUnavailableError)):
                raise classified from e
            if attempt > max_retries:
                raise
            delay = min(RETRY_BASE_DELAY_MS * (2 ** (attempt - 1)), RETRY_MAX_BACKOFF_MS)
            await asyncio.sleep((delay + random.random() * 0.25 * delay) / 1000)
