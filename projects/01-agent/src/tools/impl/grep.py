"""Grep/search tool."""

import asyncio
import shlex

from src.tools.base import BaseTool
from src.tools.executor import ToolResult


class GrepTool(BaseTool):
    name = "grep"
    description = "Search for patterns in files using grep."
    parameters = {
        "pattern": {"type": "string", "description": "Search pattern (regex)"},
        "path": {"type": "string", "description": "Directory or file to search in"},
        "recursive": {"type": "boolean", "description": "Search recursively", "optional": True},
    }

    async def execute(self, pattern: str, path: str = ".", recursive: bool = True) -> ToolResult:
        try:
            flags = "-rn" if recursive else "-n"
            cmd = f"grep {flags} {shlex.quote(pattern)} {shlex.quote(path)} 2>/dev/null || true"
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            result = stdout.decode("utf-8", errors="replace").strip()
            if not result:
                return ToolResult(f"No matches found for '{pattern}' in {path}")
            return ToolResult(result)
        except Exception as e:
            return ToolResult(f"Error searching: {e}", is_error=True)
