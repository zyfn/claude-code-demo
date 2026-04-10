"""Shell execution tool."""

import asyncio

from src.tools.base import BaseTool
from src.tools.executor import ToolResult


class BashTool(BaseTool):
    name = "bash"
    description = "Execute a shell command. Returns stdout and stderr."
    parameters = {
        "command": {"type": "string", "description": "Shell command to execute"},
        "cwd": {"type": "string", "description": "Working directory", "optional": True},
    }

    async def execute(self, command: str, cwd: str | None = None) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
