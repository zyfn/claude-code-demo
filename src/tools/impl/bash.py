"""Shell execution tool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from src.tools.types import ToolResult

_PARAMS = {
    "command": {"type": "string", "description": "Shell command to execute"},
    "cwd": {"type": "string", "description": "Working directory", "optional": True},
    "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)", "optional": True},
}


@dataclass
class BashTool:
    name: str = "bash"
    description: str = "Execute a shell command. Returns stdout, stderr, and exit code."
    parameters: dict = field(default_factory=lambda: dict(_PARAMS))

    async def execute(self, command: str, cwd: str | None = None, timeout: int = 120, **_) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            parts: list[str] = []
            if stdout:
                parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                parts.append(f"[stderr]\n{stderr.decode('utf-8', errors='replace')}")
            parts.append(f"[exit code: {proc.returncode}]")
            return ToolResult("\n".join(parts), is_error=(proc.returncode != 0))
        except asyncio.TimeoutError:
            return ToolResult(f"Command timed out after {timeout}s", is_error=True)
        except Exception as e:
            return ToolResult(f"Error: {e}", is_error=True)

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return False
