"""Grep/search tool."""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field

from src.tools.types import ToolResult


@dataclass
class GrepTool:
    name: str = "grep"
    description: str = "Search for regex patterns in files using grep."
    parameters: dict = field(default_factory=lambda: {
        "pattern": {"type": "string", "description": "Regex pattern"},
        "path": {"type": "string", "description": "Directory or file to search", "optional": True},
        "include": {"type": "string", "description": "File glob (e.g. '*.py')", "optional": True},
    })

    async def execute(self, pattern: str, path: str = ".", include: str | None = None, **_) -> ToolResult:
        try:
            parts = ["grep", "-rn"]
            if include:
                parts.extend(["--include", include])
            parts.extend([pattern, path])
            cmd = " ".join(shlex.quote(p) for p in parts) + " 2>/dev/null || true"
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            result = stdout.decode("utf-8", errors="replace").strip()
            if not result:
                return ToolResult(f"No matches for '{pattern}' in {path}")
            if len(result) > 50_000:
                result = result[:50_000] + "\n... (truncated)"
            return ToolResult(result)
        except asyncio.TimeoutError:
            return ToolResult("Search timed out", is_error=True)
        except Exception as e:
            return ToolResult(f"Error: {e}", is_error=True)

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return True
