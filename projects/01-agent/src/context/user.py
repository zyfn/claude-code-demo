"""User context — CLAUDE.md content, current date.

Mirrors Claude Code's getUserContext() in context.ts:
- memoized for the session duration
- provides claudeMd (from CLAUDE.md files) and currentDate
  for injection into the system prompt
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class UserContext(TypedDict):
    claude_md: str | None
    current_date: str


# ─── Module-level memoize ───────────────────────────────────────────────────────

_user_context_cache: UserContext | None = None
_cache_time: float = 0
_CACHE_TTL = 300  # 5 minutes for user context


def get_user_context(cwd: str) -> UserContext:
    """Return user context (CLAUDE.md + current date).

    Memoized for _CACHE_TTL seconds. Searchs up the directory tree
    for CLAUDE.md, matching Claude Code's behaviour where CLAUDE.md
    files in parent directories also apply.

    Args:
        cwd: Working directory to search from

    Returns:
        { claude_md: str | None, current_date: str }
    """
    global _user_context_cache, _cache_time

    now = time.time()
    if _user_context_cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _user_context_cache

    claude_md = load_claude_md(cwd)
    current_date = datetime.now().strftime("%Y/%m/%d")

    _user_context_cache = UserContext(
        claude_md=claude_md,
        current_date=current_date,
    )
    _cache_time = now
    return _user_context_cache


def load_claude_md(cwd: str) -> str | None:
    """Load CLAUDE.md from cwd or any parent directory.

    Searches up the directory tree, returning the first CLAUDE.md found.
    """
    path = Path(cwd).resolve()
    for parent in [path] + list(path.parents):
        md_path = parent / "CLAUDE.md"
        if md_path.is_file():
            return md_path.read_text(encoding="utf-8")
    return None


def invalidate_user_context() -> None:
    """Invalidate the user context cache. Call when CLAUDE.md changes."""
    global _user_context_cache, _cache_time
    _user_context_cache = None
    _cache_time = 0
