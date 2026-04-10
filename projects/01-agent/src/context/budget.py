"""Level 1 compression: apply_tool_result_budget.

Mirrors Claude Code's applyToolResultBudget(). Persists oversized tool
results (> per-tool maxResultSizeChars) to disk and replaces content with
a marker. Runs BEFORE micro-compact so the replacement is invisible to
the micro-compact cache (which keys only on tool_call_id).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from litellm.types.utils import Message


PERSIST_MARKER = "[result persisted to {path}, use read_file to view]"


# ─── Tool result size limits ───────────────────────────────────────────────────

# Per-tool max result sizes in characters (mirrors Claude Code's defaults).
TOOL_MAX_RESULT_SIZE: dict[str, int] = {
    "bash": 100_000,
    "read_file": 50_000,
    "grep": 50_000,
    "glob": 10_000,
}


# ─── Budget application ────────────────────────────────────────────────────────

def apply_tool_result_budget(
    messages: list[Message],
    persist_dir: str | None = None,
) -> list[Message]:
    """Truncate oversized tool results and persist to disk.

    Only persists for query sources that support it (agent mode).
    Returns a new messages list (non-mutating).

    Args:
        messages: Full message history
        persist_dir: Directory for persisted files. Created if needed.

    Returns:
        New messages list with oversized tool results replaced by markers.
    """
    if persist_dir is None:
        persist_dir = tempfile.mkdtemp(prefix="agent_context_")

    result: list[Message] = []
    for msg in messages:
        if msg.role != "tool":
            result.append(msg)
            continue

        content = _get_content(msg)
        tool_name = _infer_tool_name(msg)

        max_size = TOOL_MAX_RESULT_SIZE.get(tool_name, 50_000)
        if content and len(content) > max_size:
            path = _persist_content(content, msg.tool_call_id or tool_name, persist_dir)
            # Clone with marker content
            persisted_msg = Message(
                role="tool",
                content=PERSIST_MARKER.format(path=path),
                tool_call_id=msg.tool_call_id,
            )
            result.append(persisted_msg)
        else:
            result.append(msg)

    return result


def _infer_tool_name(msg: Message) -> str:
    """Infer tool name from tool_call_id (e.g. 'functions.bash:0' → 'bash')."""
    if msg.tool_call_id:
        parts = msg.tool_call_id.split(":")
        if len(parts) >= 2:
            return parts[1].split("_")[0]
    return "unknown"


def _persist_content(content: str, label: str, persist_dir: str) -> str:
    """Persist content to a temp file. Returns the file path."""
    os.makedirs(persist_dir, exist_ok=True)
    safe_label = "".join(c for c in label if c.isalnum() or c in "._-")
    path = Path(persist_dir) / f"{safe_label}.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _get_content(msg: Message) -> str:
    """Extract string content from a Message."""
    if isinstance(msg.content, str):
        return msg.content
    if isinstance(msg.content, list):
        return "".join(c.text for c in msg.content if hasattr(c, "text"))
    return ""
