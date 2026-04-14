"""System context — git status, cache breaker.

Mirrors Claude Code's getSystemContext() in context.ts:
- memoized for the session duration
- invalidated by cacheBreaker (time-based)
- provides gitStatus for system prompt injection
"""

from __future__ import annotations

import subprocess
import time
from typing import TypedDict


class SystemContext(TypedDict):
    git_status: str
    cache_breaker: str


# ─── Module-level memoize ───────────────────────────────────────────────────────

_system_context_cache: SystemContext | None = None
_cache_time: float = 0
_CACHE_TTL = 60  # seconds


def get_system_context(cwd: str) -> SystemContext:
    """Return system context (git status + cache breaker).

    Memoized for _CACHE_TTL seconds. Called once per session for
    system prompt injection; cacheBreaker changes each call to
    bust any stale in-memory caches downstream.

    Args:
        cwd: Working directory for git operations

    Returns:
        { git_status: str, cache_breaker: str }
    """
    global _system_context_cache, _cache_time

    now = time.time()
    if _system_context_cache is not None and (now - _cache_time) < _CACHE_TTL:
        # Refresh cacheBreaker but keep git_status
        return SystemContext(
            git_status=_system_context_cache["git_status"],
            cache_breaker=str(now),
        )

    git_status = _get_git_status(cwd)
    _system_context_cache = SystemContext(
        git_status=git_status,
        cache_breaker=str(now),
    )
    _cache_time = now
    return _system_context_cache


def _get_git_status(cwd: str) -> str:
    """Get current git status summary."""
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=cwd, text=True
        ).strip() or "(detached)"
        status = subprocess.check_output(
            ["git", "status", "--short"], cwd=cwd, text=True
        ).strip()
        log = subprocess.check_output(
            ["git", "log", "-1", "--format=%h %s (%cr)"], cwd=cwd, text=True
        ).strip()
        result = f"Branch: {branch}\nLast commit: {log}"
        if status:
            lines = status.split("\n")
            result += f"\nChanges ({len(lines)} files):\n{status[:500]}"
        return result
    except Exception:
        return "(not a git repo or git not available)"
