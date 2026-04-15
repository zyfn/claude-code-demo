"""Unified hook system with matcher support and config file loading.

Two ways to register hooks:
1. Code: registry.on("PreToolUse", handler, matcher="bash")
2. Config: .ccc/hooks.yaml → loaded at startup

Config example (.ccc/hooks.yaml):
    PreToolUse:
      - matcher: bash
        hooks:
          - type: command
            command: "echo checking: $TOOL_INPUT"
      - hooks:
          - type: command
            command: "echo all tools"
    Stop:
      - hooks:
          - type: command
            command: "echo query completed"
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

# Handler: async (input_dict) → Any
HookHandler = Callable[[dict[str, Any]], Awaitable[Any]]

from enum import Enum


class HookEvent(str, Enum):
    """Hook event names. Using Enum prevents typos — misspelled names fail at import."""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"
    # Future:
    # PRE_LLM_CALL = "PreLLMCall"
    # POST_LLM_CALL = "PostLLMCall"
    # SESSION_START = "SessionStart"
    # SESSION_END = "SessionEnd"


# ━━ Registered hook entry ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class _HookEntry:
    handler: HookHandler
    matcher: str | None = None  # None = match all


def _matches(matcher: str | None, input: dict[str, Any]) -> bool:
    """Check if a matcher matches the dispatch input.

    For PreToolUse/PostToolUse: matches against input["call"].name
    For other events: None matcher always matches, string matcher is ignored
    """
    if matcher is None:
        return True
    call = input.get("call")
    if call is None:
        return False
    tool_name = getattr(call, "name", None) or call.get("name", "")
    return bool(re.fullmatch(matcher, tool_name, re.IGNORECASE))


# ━━ Command hook (config-driven) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _CommandHook:
    """A hook that runs a shell command. Loaded from config."""

    def __init__(self, command: str, timeout: int = 30):
        self._command = command
        self._timeout = timeout

    async def __call__(self, input: dict[str, Any]) -> Any:
        env_input = json.dumps({
            k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
            for k, v in input.items()
        }, default=str)

        # Pass as environment variable — safe from shell injection
        env = {"TOOL_INPUT": env_input}
        try:
            proc = await asyncio.create_subprocess_shell(
                self._command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**__import__("os").environ, **env},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            # Exit code 2 = blocking (Claude Code convention)
            if proc.returncode == 2:
                from src.tools.types import ToolResult
                msg = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
                return ToolResult(f"Hook blocked: {msg}", is_error=True)
            return None
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None


# ━━ Registry ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class HookRegistry:
    """Central registry for all hooks. Supports matcher filtering."""

    def __init__(self) -> None:
        self._entries: dict[str, list[_HookEntry]] = defaultdict(list)

    def on(self, event: str, handler: HookHandler, matcher: str | None = None) -> None:
        """Register a handler. matcher filters by tool name (regex, optional)."""
        self._entries[event].append(_HookEntry(handler=handler, matcher=matcher))

    async def dispatch(self, event: str, input: dict[str, Any]) -> list[Any]:
        """Run all matching handlers for an event. Returns list of results."""
        results: list[Any] = []
        for entry in self._entries.get(event, []):
            if _matches(entry.matcher, input):
                result = await entry.handler(input)
                results.append(result)
        return results

    def load_from_file(self, path: str | Path) -> int:
        """Load hooks from a YAML config file. Returns number of hooks loaded.

        Format:
            PreToolUse:
              - matcher: bash        # optional, regex
                hooks:
                  - type: command
                    command: "echo $TOOL_INPUT"
                    timeout: 30      # optional, seconds
        """
        p = Path(path)
        if not p.is_file():
            return 0

        config = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            return 0

        count = 0
        for event_name, matchers in config.items():
            if not isinstance(matchers, list):
                continue
            for matcher_block in matchers:
                matcher = matcher_block.get("matcher")
                for hook_def in matcher_block.get("hooks", []):
                    hook_type = hook_def.get("type")
                    if hook_type == "command":
                        handler = _CommandHook(
                            command=hook_def["command"],
                            timeout=hook_def.get("timeout", 30),
                        )
                        self.on(event_name, handler, matcher=matcher)
                        count += 1
        return count
