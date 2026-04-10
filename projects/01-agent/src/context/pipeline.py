"""Context compression pipeline.

Mirrors Claude Code's context compaction pipeline (query.ts lines 365-548).
Applies compression levels in order before each LLM call:

    1. apply_tool_result_budget   → persist oversized tool results
    2. snip_compact_if_needed     → remove matching human messages
    3. micro_compact              → deduplicate tool results
    4. apply_collapses_if_needed  → projected view (future work)
    5. auto_compact               → LLM summarization (threshold-based)

Each stage returns a (messages, stats) pair; the next stage
receives the output of the previous.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Awaitable

from litellm.types.utils import Message

from .budget import apply_tool_result_budget
from .micro import micro_compact
from .compact import (
    auto_compact,
    should_auto_compact,
    AutoCompactResult,
    AutoCompactTracking,
    AUTO_COMPACT_BUFFER,
)


@dataclass
class PipelineResult:
    """Result of running the full compression pipeline."""
    messages: list[Message]
    compaction_result: AutoCompactResult | None
    budget_truncated_count: int
    micro_deleted_count: int
    snip_boundary: int


class ContextPipeline:
    """Chains all context compression levels in order.

    Each level is applied sequentially; results flow from one stage to the next.
    """

    def __init__(
        self,
        count_tokens: Callable[[list[Message], list[dict] | None], int],
        resolve_limit: Callable[[], int],
        microcompact_fn: Callable[[list[Message]], tuple[list[Message], int]] | None = None,
        autocompact_fn: Callable[
            [list[Message], object], Awaitable[AutoCompactResult | None]
        ] | None = None,
        llm_client: object = None,
        ratio: float = 0.8,
        persist_dir: str | None = None,
    ):
        self._count_tokens = count_tokens
        self._resolve_limit = resolve_limit
        self._microcompact = microcompact_fn or micro_compact
        self._autocompact = autocompact_fn
        self._llm_client = llm_client
        self._ratio = ratio
        self._persist_dir = persist_dir

    async def run(
        self,
        messages: list[Message],
        tracking: AutoCompactTracking | None,
    ) -> PipelineResult:
        """Run all compression stages.

        Args:
            messages: Current message history
            tracking: Auto-compact tracking state (for circuit breaker)

        Returns:
            PipelineResult with processed messages and stats.
        """
        current = list(messages)

        # ── Stage 1: apply_tool_result_budget ────────────────────────────────
        current = apply_tool_result_budget(current, self._persist_dir)
        budget_count = sum(
            1 for m in messages
            if m.role == "tool"
            and "[result persisted" in (m.content or "")
        )

        # ── Stage 2: snip_compact_if_needed ────────────────────────────────
        # Future: implement snip_compact_if_needed
        snip_boundary = 0

        # ── Stage 3: micro_compact ─────────────────────────────────────────
        current, micro_count = self._microcompact(current)

        # ── Stage 4: apply_collapses_if_needed ────────────────────────────
        # Future: implement projected view collapses

        # ── Stage 5: auto_compact (only if threshold met) ─────────────────
        compaction_result: AutoCompactResult | None = None
        if self._autocompact:
            should = should_auto_compact(
                current,
                self._count_tokens,
                self._resolve_limit,
                tracking,
                self._ratio,
            )
            if should:
                compaction_result = await self._autocompact(
                    current,
                    self._llm_client,
                )
                if compaction_result and compaction_result.post_compact_messages:
                    current = compaction_result.post_compact_messages

        return PipelineResult(
            messages=current,
            compaction_result=compaction_result,
            budget_truncated_count=budget_count,
            micro_deleted_count=micro_count,
            snip_boundary=snip_boundary,
        )
