"""Enhanced context manager with multi-level compression.

Level 1 (per-turn): truncateLargeResults — persist oversized tool results to disk
Level 2 (per-turn): microCompact — remove duplicate file reads
Level 3 (on threshold): autoCompact — LLM-based summarization
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from litellm.types.utils import Message


# Marker placed in message content when result is persisted to disk.
PERSIST_MARKER = "[result persisted to {path}, use read_file to view]"


class ContextManager:
    """Context manager with multi-level compression for long conversations."""

    def __init__(
        self,
        messages: list[Message],
        count_tokens: Callable[[list[Message], list[dict] | None], int],
        resolve_limit: Callable[[], int],
        ratio: float = 0.8,
        persist_dir: str | None = None,
    ):
        self._messages = messages
        self._count_tokens = count_tokens
        self._resolve_limit = resolve_limit
        self._ratio = ratio
        self._limit: int | None = None
        self._persist_dir = persist_dir or tempfile.mkdtemp(prefix="agent_context_")

    def resolve_limit(self) -> int:
        if self._limit is None:
            result = self._resolve_limit()
            self._limit = int(result) if result else 128_000
        return self._limit

    def count(self, tools: list[dict] | None = None) -> int:
        return self._count_tokens(self._messages, tools)

    # ─── Level 1: Truncate large tool results ────────────────────────────────

    def truncate_large_results(self, tools: list[dict] | None = None) -> list[Message]:
        """Truncate oversized tool results and persist to disk.

        Returns list of removed messages (for event emission).
        """
        removed = []
        for i, msg in enumerate(self._messages):
            if not _is_tool_result(msg):
                continue
            content = _get_content(msg)
            if content and len(content) > 50_000:
                # Persist to disk
                path = self._persist_content(content, msg.tool_call_id or f"tool_{i}")
                # Replace content with marker
                msg.content = PERSIST_MARKER.format(path=path)
                removed.append(msg)
        return removed

    def _persist_content(self, content: str, label: str) -> str:
        """Persist content to a temp file. Returns the file path."""
        os.makedirs(self._persist_dir, exist_ok=True)
        safe_label = "".join(c for c in label if c.isalnum() or c in "._-")
        path = Path(self._persist_dir) / f"{safe_label}.txt"
        path.write_text(content, encoding="utf-8")
        return str(path)

    # ─── Level 2: Micro-compact (remove duplicate file reads) ───────────────

    def micro_compact(self, tools: list[dict] | None = None) -> list[Message]:
        """Remove duplicate file reads, keeping only the most recent.

        Returns list of removed messages.
        """
        seen: dict[str, int] = {}  # path -> last message index
        to_remove: list[int] = []

        for i, msg in enumerate(self._messages):
            if not _is_tool_result(msg):
                continue
            content = _get_content(msg)
            if not content:
                continue
            # Try to extract file path from the tool call
            # This is heuristic: look for "Reading <path>" or "File: <path>" patterns
            import re
            path_match = re.search(r"(?:Reading|File:\s*)([^\n]+)", content[:200])
            if path_match:
                path_key = path_match.group(1).strip()
                if path_key in seen:
                    # Duplicate — mark earlier one for removal
                    to_remove.append(seen[path_key])
                seen[path_key] = i

        # Remove in reverse order to preserve indices
        removed = []
        for idx in sorted(to_remove, reverse=True):
            removed.append(self._messages.pop(idx))
        return removed

    # ─── Level 3: Auto-compact (LLM summarization) ──────────────────────────

    async def auto_compact(
        self,
        tools: list[dict] | None,
        llm_client: "LLMClientProtocol | None",
        summary_prompt: str = "Summarize the following conversation concisely, preserving key facts and decisions:",
    ) -> list[Message]:
        """Compact old messages using LLM summarization when token threshold exceeded.

        This is a best-effort approach when an LLM client is available.
        """
        if llm_client is None:
            return []

        limit = self.resolve_limit()
        threshold = int(limit * self._ratio)
        current = self.count(tools)
        if current < threshold:
            return []

        # Find a good compact boundary: after system prompt, before recent messages
        boundary = self._find_compact_boundary()
        if boundary <= 1:
            return []

        messages_to_summarize = self._messages[1:boundary]  # Exclude system prompt
        if not messages_to_summarize:
            return []

        try:
            summary = await _generate_summary(llm_client, messages_to_summarize, summary_prompt)
        except Exception:
            return []

        # Mark boundary and keep messages after it
        compact_msg = Message(
            role="system",
            content=f"[Earlier conversation summarized: {summary}]",
        )
        self._messages = [self._messages[0], compact_msg] + self._messages[boundary:]
        return messages_to_summarize

    def _find_compact_boundary(self) -> int:
        """Find a good place to split messages for compaction.

        Returns index of first message to keep (after system prompt).
        """
        # Keep at least system + 2 messages
        if len(self._messages) <= 3:
            return 0

        # Find a natural break point: after last tool result before recent turns
        tool_result_indices = [
            i for i, m in enumerate(self._messages)
            if _is_tool_result(m)
        ]
        if not tool_result_indices:
            return len(self._messages) // 2

        # Keep the last 4 messages (approximately the last 2 turns)
        return max(1, tool_result_indices[-4] if len(tool_result_indices) >= 4 else 1)

    def trim(self) -> Message | None:
        """Remove oldest non-system message. Returns the removed message."""
        if len(self._messages) <= 3:
            return None
        return self._messages.pop(1)

    def maybe_trim(self, tools: list[dict] | None = None) -> list[Message]:
        """Trim until token count is within threshold. Returns trimmed messages."""
        limit = self.resolve_limit()
        threshold = int(limit * self._ratio)
        current = self.count(tools)
        removed = []
        while current > threshold and len(self._messages) > 3:
            msg = self.trim()
            if msg:
                removed.append(msg)
            current = self.count(tools)
        return removed

    async def apply_compactions(
        self,
        tools: list[dict] | None = None,
        llm_client: "LLMClientProtocol | None" = None,
    ) -> dict[str, list[Message]]:
        """Run all compaction levels. Returns stats on what was removed."""
        stats: dict[str, list[Message]] = {}

        # Level 1: truncate large results
        stats["truncated"] = self.truncate_large_results(tools)

        # Level 2: micro compact
        stats["micro_compact"] = self.micro_compact(tools)

        # Level 3: auto compact (async, only if needed)
        if llm_client:
            try:
                stats["auto_compact"] = await self.auto_compact(tools, llm_client)
            except Exception:
                pass

        return stats


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _is_tool_result(msg: Message) -> bool:
    return msg.role == "tool"


def _get_content(msg: Message) -> str:
    if isinstance(msg.content, str):
        return msg.content
    if isinstance(msg.content, list):
        return "".join(
            c.text for c in msg.content if hasattr(c, "text")
        )
    return ""


async def _generate_summary(
    client: "LLMClientProtocol",
    messages: list[Message],
    prompt: str,
) -> str:
    """Use LLM to generate a summary of messages."""
    from litellm.types.utils import Message as LLMMessage

    summary_messages = [
        LLMMessage(role="user", content=prompt),
        LLMMessage(
            role="user",
            content="\n\n".join(
                f"[{m.role}]: {_get_content(m)}" for m in messages
            ),
        ),
    ]

    text = ""
    async for chunk in client.chat(summary_messages, max_tokens=1024):
        if hasattr(chunk, "choices") and chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text += delta.content
    return text.strip()
