"""File system tools: read, write, edit, create directory."""

import os
from pathlib import Path
from src.tools.base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Supports text files."
    parameters = {
        "path": {"type": "string", "description": "Path to the file to read"},
        "offset": {"type": "integer", "description": "Line number to start from (1-indexed)"},
        "limit": {"type": "integer", "description": "Maximum lines to read"},
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


class BashTool(BaseTool):
    name = "bash"
    description = "Execute a shell command. Returns stdout and stderr."
    parameters = {
        "command": {"type": "string", "description": "Shell command to execute"},
        "cwd": {"type": "string", "description": "Working directory (optional)"},
    }

    async def execute(self, command: str, cwd: str | None = None) -> ToolResult:
        try:
            proc = await __import__("asyncio").create_subprocess_shell(
                command,
                stdout=__import__("asyncio").subprocess.PIPE,
                stderr=__import__("asyncio").subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await proc.communicate()
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            output += f"\n[exit code: {proc.returncode}]"
            return ToolResult(output, is_error=(proc.returncode != 0))
        except Exception as e:
            return ToolResult(f"Error executing command: {e}", is_error=True)


class GrepTool(BaseTool):
    name = "grep"
    description = "Search for patterns in files using grep."
    parameters = {
        "pattern": {"type": "string", "description": "Search pattern (regex)"},
        "path": {"type": "string", "description": "Directory or file to search in"},
        "recursive": {"type": "boolean", "description": "Search recursively"},
    }

    async def execute(self, pattern: str, path: str = ".", recursive: bool = True) -> ToolResult:
        try:
            flags = "-rn" if recursive else "-n"
            cmd = f"grep {flags} --include='*.py' --include='*.js' --include='*.ts' --include='*.md' --include='*.json' '{pattern}' {path} 2>/dev/null || true"
            proc = await __import__("asyncio").create_subprocess_shell(
                cmd,
                stdout=__import__("asyncio").subprocess.PIPE,
                stderr=__import__("asyncio").subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            result = stdout.decode("utf-8", errors="replace").strip()
            if not result:
                return ToolResult(f"No matches found for '{pattern}' in {path}")
            return ToolResult(result)
        except Exception as e:
            return ToolResult(f"Error searching: {e}", is_error=True)
