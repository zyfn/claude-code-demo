"""File tools: read, write, edit."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.tools.types import ToolResult


@dataclass
class ReadFileTool:
    name: str = "read_file"
    description: str = "Read file contents. Supports offset/limit for large files."
    parameters: dict = field(default_factory=lambda: {
        "path": {"type": "string", "description": "File path to read"},
        "offset": {"type": "integer", "description": "Start line (1-indexed)", "optional": True},
        "limit": {"type": "integer", "description": "Max lines to read", "optional": True},
    })

    async def execute(self, path: str, offset: int = 1, limit: int | None = None, **_) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(f"File not found: {path}", is_error=True)
            if not p.is_file():
                return ToolResult(f"Not a file: {path}", is_error=True)
            lines = p.read_text(encoding="utf-8").splitlines()
            total = len(lines)
            start = max(0, offset - 1)
            end = start + limit if limit else total
            chunk = lines[start:end]
            header = f"[lines {start + 1}-{min(end, total)} of {total}]\n" if total > len(chunk) else ""
            return ToolResult(header + "\n".join(chunk))
        except Exception as e:
            return ToolResult(f"Error: {e}", is_error=True)

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return True


@dataclass
class WriteFileTool:
    name: str = "write_file"
    description: str = "Create or overwrite a file. Creates parent directories."
    parameters: dict = field(default_factory=lambda: {
        "path": {"type": "string", "description": "File path"},
        "content": {"type": "string", "description": "Content to write"},
    })

    async def execute(self, path: str, content: str, **_) -> ToolResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(f"Wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(f"Error: {e}", is_error=True)

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return False


@dataclass
class EditFileTool:
    name: str = "edit_file"
    description: str = "Edit a file by replacing exact text. old_string must match exactly once."
    parameters: dict = field(default_factory=lambda: {
        "path": {"type": "string", "description": "File path"},
        "old_string": {"type": "string", "description": "Exact text to find"},
        "new_string": {"type": "string", "description": "Replacement text"},
    })

    async def execute(self, path: str, old_string: str, new_string: str, **_) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(f"File not found: {path}", is_error=True)
            content = p.read_text(encoding="utf-8")
            count = content.count(old_string)
            if count == 0:
                return ToolResult("old_string not found in file", is_error=True)
            if count > 1:
                return ToolResult(f"old_string matches {count} locations — must be unique", is_error=True)
            p.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
            return ToolResult(f"Edited {path}")
        except Exception as e:
            return ToolResult(f"Error: {e}", is_error=True)

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return False
