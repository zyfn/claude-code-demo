"""File operation tools: read, write, edit."""

from pathlib import Path

from src.tools.base import BaseTool
from src.tools.executor import ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Supports text files."
    parameters = {
        "path": {"type": "string", "description": "Path to the file to read"},
        "offset": {"type": "integer", "description": "Line number to start from (1-indexed)", "optional": True},
        "limit": {"type": "integer", "description": "Maximum lines to read", "optional": True},
    }

    async def execute(self, path: str, offset: int = 1, limit: int | None = None) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(f"Error: File not found: {path}", is_error=True)
            lines = p.read_text(encoding="utf-8").splitlines()
            start = max(0, offset - 1)
            end = start + limit if limit else len(lines)
            chunk = lines[start:end]
            total = len(lines)
            header = f"[{start+1}-{min(end, total)} of {total} lines]" if total > (end - start) else ""
            return ToolResult(header + "\n" + "\n".join(chunk))
        except Exception as e:
            return ToolResult(f"Error reading file: {e}", is_error=True)


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Create or overwrite a file with content. Creates parent directories automatically."
    parameters = {
        "path": {"type": "string", "description": "Path to the file to write"},
        "content": {"type": "string", "description": "Content to write"},
    }

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(f"Successfully wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(f"Error writing file: {e}", is_error=True)


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Make precise edits to a file by replacing exact text. The old_string must match exactly."
    parameters = {
        "path": {"type": "string", "description": "Path to the file to edit"},
        "old_string": {"type": "string", "description": "Exact text to find and replace"},
        "new_string": {"type": "string", "description": "New text to replace with"},
    }

    async def execute(self, path: str, old_string: str, new_string: str) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(f"Error: File not found: {path}", is_error=True)
            content = p.read_text(encoding="utf-8")
            if old_string not in content:
                return ToolResult("Error: old_string not found in file", is_error=True)
            new_content = content.replace(old_string, new_string, 1)
            p.write_text(new_content, encoding="utf-8")
            return ToolResult(f"Successfully edited {path}")
        except Exception as e:
            return ToolResult(f"Error editing file: {e}", is_error=True)
