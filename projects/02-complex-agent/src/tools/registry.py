"""Tool registry — returns the default tool pool."""

from __future__ import annotations

from src.tools.types import Tool
from src.tools.impl.bash import BashTool
from src.tools.impl.file import ReadFileTool, WriteFileTool, EditFileTool
from src.tools.impl.grep import GrepTool


def get_default_tools() -> list[Tool]:
    all_tools: list[Tool] = [BashTool(), ReadFileTool(), WriteFileTool(), EditFileTool(), GrepTool()]
    return [t for t in all_tools if t.is_enabled()]
