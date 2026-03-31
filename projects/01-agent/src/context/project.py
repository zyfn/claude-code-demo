"""Project context: file tree, git status, relevant files."""

import os
from pathlib import Path


class ProjectContext:
    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()

    def get_file_tree(self, max_depth: int = 3) -> str:
        """Generate a file tree string for the project."""
        lines = [f"📁 {self.root.name}/"]
        self._walk(self.root, lines, "", max_depth, 0)
        return "\n".join(lines)

    def _walk(self, path: Path, lines: list, prefix: str, max_depth: int, depth: int):
        if depth >= max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return
        dirs = [e for e in entries if e.is_dir() and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and not e.name.startswith(".")]
        # Skip common noise
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
        """Get current git status summary."""
        import subprocess
        try:
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=self.root, text=True
            ).strip() or "(detached)"
            status = subprocess.check_output(
                ["git", "status", "--short"], cwd=self.root, text=True
            ).strip()
            log = subprocess.check_output(
                ["git", "log", "-1", "--format=%h %s (%cr)"], cwd=self.root, text=True
            ).strip()
            result = f"Branch: {branch}\nLast commit: {log}"
            if status:
                lines = status.split("\n")
                result += f"\nChanges ({len(lines)} files):\n{status[:500]}"
            return result
        except Exception:
            return "(not a git repo or git not available)"

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
