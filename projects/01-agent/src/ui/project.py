"""Project context — file tree and git status for TUI display.

Mirrors Claude Code's ProjectContext for display purposes.
Not used in the actual agent loop context compression.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


class ProjectContext:
    """Project context with file tree and git status caching (display use only)."""

    CACHE_TTL = 60

    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self._file_tree_cache: str | None = None
        self._file_tree_mtime: float = 0
        self._git_status_cache: str | None = None
        self._git_status_mtime: float = 0

    def _get_dir_mtime(self) -> float:
        try:
            mtime = self.root.stat().st_mtime
            for entry in self.root.rglob("*"):
                try:
                    mtime = max(mtime, entry.stat().st_mtime)
                except (OSError, PermissionError):
                    continue
            return mtime
        except (OSError, PermissionError):
            return 0

    def _get_git_mtime(self) -> float:
        git_head = self.root / ".git" / "HEAD"
        try:
            return git_head.stat().st_mtime if git_head.exists() else 0
        except OSError:
            return 0

    def _is_cache_valid(self, cached_mtime: float, current_mtime: float) -> bool:
        if cached_mtime == 0:
            return False
        age = time.time() - cached_mtime
        return age < self.CACHE_TTL and cached_mtime >= current_mtime

    def get_file_tree(self, max_depth: int = 3) -> str:
        current_mtime = self._get_dir_mtime()
        if self._is_cache_valid(self._file_tree_mtime, current_mtime):
            return self._file_tree_cache or ""
        lines = [f"📁 {self.root.name}/"]
        self._walk(self.root, lines, "", max_depth, 0)
        self._file_tree_cache = "\n".join(lines)
        self._file_tree_mtime = time.time()
        return self._file_tree_cache

    def _walk(self, path: Path, lines: list, prefix: str, max_depth: int, depth: int):
        if depth >= max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return
        dirs = [e for e in entries if e.is_dir() and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and not e.name.startswith(".")]
        skip_dirs = {"__pycache__", "node_modules", ".git", ".venv", "venv", "dist", "build"}
        dirs = [d for d in dirs if d.name not in skip_dirs]
        all_items = dirs + files
        for i, item in enumerate(all_items):
            is_last = i == len(all_items) - 1
            connector = "└── " if is_last else "├── "
            if item.is_dir():
                lines.append(f"{prefix}{connector}📁 {item.name}/")
                ext = "    " if is_last else "│   "
                self._walk(item, lines, prefix + ext, max_depth, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{item.name}")

    def get_git_status(self) -> str:
        current_mtime = self._get_git_mtime()
        if self._is_cache_valid(self._git_status_mtime, current_mtime):
            return self._git_status_cache or ""
        result = _get_git_status(str(self.root))
        self._git_status_cache = result
        self._git_status_mtime = time.time()
        return result

    def get_context_summary(self) -> str:
        return f"""## Project Context
**Root:** `{self.root}`

### File Tree
```
{self.get_file_tree()}
```

### Git Status
```
{self.get_git_status()}
```"""

    def invalidate_cache(self) -> None:
        self._file_tree_cache = None
        self._file_tree_mtime = 0
        self._git_status_cache = None
        self._git_status_mtime = 0


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
