"""Retry logic for the agent loop — follows Claude Code's withRetry pattern.

Wraps LLM calls with:
- Exponential backoff with jitter
- Token overflow adjustment
- Model fallback
- Error classification (rate limit, prompt too long, etc.)
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from litellm.types.utils import StreamingChatCompletionChunk


# ─── Config ────────────────────────────────────────────────────────────────────

BASE_DELAY_MS = 500
DEFAULT_MAX_RETRIES = 5
MAX_BACKOFF_MS = 32_000


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay_ms: float = BASE_DELAY_MS
    max_backoff_ms: float = MAX_BACKOFF_MS
    max_context_collapse: int = 3
    max_reactive_compact: int = 2
    max_output_recovery: int = 3
    initial_max_output_tokens: int = 8192
    max_output_escalation: int = 64000


# ─── Error Types ───────────────────────────────────────────────────────────────

class AgentRetryError(Exception):
    """Base class for errors that may be recoverable."""
    pass


class PromptTooLongError(AgentRetryError):
    """Context window overflow."""
    pass


class RateLimitError(AgentRetryError):
    """Rate limit hit — backoff and retry."""
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class MaxOutputTokensError(AgentRetryError):
    """Model hit max output tokens limit."""
    pass


class ModelUnavailableError(AgentRetryError):
    """Primary model unavailable."""
    pass


# ─── Retry State ──────────────────────────────────────────────────────────────

@dataclass
class RetryState:
    """Carries state across retry attempts."""
    context_collapse_count: int = 0
    reactive_compact_count: int = 0
    max_output_tokens_count: int = 0
    max_output_tokens_override: int | None = None
    rate_limit_backoff: float = 1.0
    model_fallback_count: int = 0
    last_error: Exception | None = None


# ─── Detection Helpers ─────────────────────────────────────────────────────────

def detect_rate_limit(error: Exception) -> bool:
    msg = str(error).lower()
    return any(kw in msg for kw in ["rate limit", "429", "too many requests", "rate_limit"])


def detect_model_unavailable(error: Exception) -> bool:
    msg = str(error).lower()
    return any(kw in msg for kw in ["model not found", "model unavailable", "404", "invalid model"])


def is_prompt_too_long(error: Exception) -> bool:
    msg = str(error).lower()
    return any(kw in msg for kw in ["prompt too long", "context_length", "maximum context", "too many tokens", "context_limit_exceeded"])


def is_max_output_tokens(error: Exception) -> bool:
    msg = str(error).lower()
    return any(kw in msg for kw in ["max output tokens", "maximum output", "response too long"])


def map_error(e: Exception) -> AgentRetryError:
    """Map an exception to an AgentRetryError type."""
    if is_prompt_too_long(e):
        return PromptTooLongError(str(e))
    elif detect_rate_limit(e):
        retry_after = None
        if hasattr(e, "retry_after"):
            retry_after = getattr(e, "retry_after")
        elif hasattr(e, "response"):
            # Try to get Retry-After header
            resp = getattr(e, "response", None)
            if resp and hasattr(resp, "headers"):
                ra = resp.headers.get("retry-after")
                if ra:
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
        return RateLimitError(str(e), retry_after)
    elif is_max_output_tokens(e):
        return MaxOutputTokensError(str(e))
    elif detect_model_unavailable(e):
        return ModelUnavailableError(str(e))
    return e


# ─── Core Retry Logic ──────────────────────────────────────────────────────────

@dataclass
class RetryAction:
    """Result of a recovery decision."""
    action: str  # "continue", "retry", "fallback", "fail"
    message: str = ""
    new_max_tokens: int | None = None
    new_state: RetryState | None = None


def compute_retry_delay(attempt: int, retry_after: float | None, max_delay: float) -> float:
    """Compute delay with exponential backoff and jitter."""
    if retry_after is not None:
        return min(retry_after * 1000, max_delay)
    base = min(BASE_DELAY_MS * (2 ** (attempt - 1)), max_delay)
    jitter = random.random() * 0.25 * base
    return base + jitter


async def with_retry(
    call_model: Callable,
    messages: list,
    tools: list | None,
    config: RetryConfig,
    state: RetryState,
    max_tokens: int | None = None,
) -> "AsyncGenerator[StreamingChatCompletionChunk, None]":
    """Call the model with retry logic.

    Yields chunks from the streaming response.
    Raises on unrecoverable error.

    Usage:
        async for chunk in with_retry(client.chat, messages, tools, config, state):
            yield chunk
    """
    override_max_tokens = state.max_output_tokens_override or max_tokens

    for attempt in range(1, config.max_retries + 2):
        try:
            # Note: call_model() returns an async generator directly (async def that yields),
            # not a coroutine. So we iterate without await.
            async for chunk in call_model(messages, tools, override_max_tokens):
                yield chunk
            return  # Success
        except Exception as e:
            state.last_error = e
            mapped = map_error(e)

            if isinstance(mapped, MaxOutputTokensError):
                action = _handle_max_output_tokens(mapped, config, state)
            elif isinstance(mapped, RateLimitError):
                action = _handle_rate_limit(mapped, config, state)
            elif isinstance(mapped, PromptTooLongError):
                action = _handle_prompt_too_long(mapped, config, state)
            elif isinstance(mapped, ModelUnavailableError):
                action = _handle_model_unavailable(mapped, config, state)
            else:
                # Unknown error — don't retry
                raise

            match action.action:
                case "continue":
                    # Token overflow was adjusted, retry immediately
                    if action.new_max_tokens:
                        override_max_tokens = action.new_max_tokens
                    continue
                case "retry":
                    # Backoff then retry — update override_max_tokens if adjusted
                    if action.new_max_tokens:
                        override_max_tokens = action.new_max_tokens
                    delay = compute_retry_delay(
                        attempt,
                        mapped.retry_after if isinstance(mapped, RateLimitError) else None,
                        config.max_backoff_ms,
                    )
                    await asyncio.sleep(delay / 1000)
                    continue
                case "fallback":
                    raise ModelUnavailableError(f"Fallback not available: {mapped.message}")
                case "fail":
                    raise
                case _:
                    raise


def _handle_max_output_tokens(
    error: MaxOutputTokensError,
    config: RetryConfig,
    state: RetryState,
) -> RetryAction:
    # Try 1: Escalate token limit
    if state.max_output_tokens_override is None:
        escalated = min(config.initial_max_output_tokens * 4, config.max_output_escalation)
        state.max_output_tokens_override = escalated
        return RetryAction(
            action="continue",
            message=f"Escalated max_output_tokens to {escalated}",
            new_max_tokens=escalated,
            new_state=state,
        )
    # Try 2: Inject recovery prompt
    if state.max_output_tokens_count < config.max_output_recovery:
        state.max_output_tokens_count += 1
        return RetryAction(
            action="continue",
            message=f"Max output recovery attempt {state.max_output_tokens_count}",
            new_state=state,
        )
    return RetryAction(action="fail", message="Max output tokens recovery exhausted")


def _handle_rate_limit(
    error: RateLimitError,
    config: RetryConfig,
    state: RetryState,
) -> RetryAction:
    backoff = state.rate_limit_backoff
    if error.retry_after:
        backoff = max(backoff, error.retry_after)
    else:
        backoff = min(backoff * 2, config.max_backoff_ms / 1000)
    state.rate_limit_backoff = backoff
    return RetryAction(
        action="retry",
        message=f"Rate limited, backing off {backoff}s",
        new_state=state,
    )


def _handle_prompt_too_long(
    error: PromptTooLongError,
    config: RetryConfig,
    state: RetryState,
) -> RetryAction:
    # Note: actual context compaction is handled by the caller via deps.
    # This just counts attempts.
    if state.context_collapse_count < config.max_context_collapse:
        state.context_collapse_count += 1
        return RetryAction(
            action="continue",
            message="Context collapse attempted",
            new_state=state,
        )
    if state.reactive_compact_count < config.max_reactive_compact:
        state.reactive_compact_count += 1
        return RetryAction(
            action="retry",
            message="Reactive compact attempted",
            new_state=state,
        )
    return RetryAction(action="fail", message="Prompt too long recovery exhausted")


def _handle_model_unavailable(
    error: ModelUnavailableError,
    config: RetryConfig,
    state: RetryState,
) -> RetryAction:
    if state.model_fallback_count < 2:
        state.model_fallback_count += 1
        return RetryAction(
            action="fallback",
            message=f"Model fallback {state.model_fallback_count}",
            new_state=state,
        )
    return RetryAction(action="fail", message="Model unavailable and no fallbacks")
