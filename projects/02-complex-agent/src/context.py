"""Context gathering — system + user context. Called at session start."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def get_system_context(cwd: str) -> dict[str, str]:
    ctx: dict[str, str] = {}
    git = _git_status(cwd)
    if git:
        ctx["git_status"] = git
    return ctx


def get_user_context(cwd: str) -> dict[str, str]:
    ctx: dict[str, str] = {"current_date": f"Today is {datetime.now().strftime('%Y-%m-%d')}."}
    claude_md = load_claude_md(cwd)
    if claude_md:
        ctx["claude_md"] = claude_md
    return ctx


def load_claude_md(cwd: str) -> str | None:
    path = Path(cwd).resolve()
    for parent in [path, *path.parents]:
        md = parent / "CLAUDE.md"
        if md.is_file():
            return md.read_text(encoding="utf-8")
    return None


def _git_status(cwd: str) -> str | None:
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=cwd, text=True, timeout=5
        ).strip() or "(detached)"
        status = subprocess.check_output(
            ["git", "status", "--short"], cwd=cwd, text=True, timeout=5
        ).strip()
        log = subprocess.check_output(
            ["git", "log", "-1", "--format=%h %s (%cr)"], cwd=cwd, text=True, timeout=5
        ).strip()
        result = f"Branch: {branch}\nLast commit: {log}"
        if status:
            lines = status.split("\n")
            result += f"\nChanges ({len(lines)} files):\n{status[:500]}"
        return result
    except Exception:
        return None
