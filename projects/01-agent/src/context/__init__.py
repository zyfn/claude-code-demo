"""Context management — compression pipeline, system/user context.

Modules:
- system.py: get_system_context() (memoized)
- user.py: get_user_context() (memoized) + load_claude_md()
- pipeline.py: ContextPipeline — chains all compression levels
- budget.py: Level 1 — apply_tool_result_budget()
- snip.py: Level 2 — snip_compact_if_needed() (stub)
- micro.py: Level 3 — micro_compact() by tool_call_id deduplication
- compact.py: Level 4/5 — auto_compact() with threshold + circuit breaker
"""

from __future__ import annotations

from .system import get_system_context
from .user import get_user_context, load_claude_md
from .pipeline import ContextPipeline, PipelineResult
from .budget import apply_tool_result_budget
from .snip import snip_compact_if_needed, SnipResult
from .micro import micro_compact
from .compact import (
    auto_compact,
    should_auto_compact,
    AutoCompactResult,
    AutoCompactTracking,
    AUTO_COMPACT_BUFFER,
    MAX_CONSECUTIVE_FAILURES,
)

__all__ = [
    # System / User context
    "get_system_context",
    "get_user_context",
    "load_claude_md",
    # Pipeline
    "ContextPipeline",
    "PipelineResult",
    # Compression levels
    "apply_tool_result_budget",
    "snip_compact_if_needed",
    "SnipResult",
    "micro_compact",
    "auto_compact",
    "should_auto_compact",
    "AutoCompactResult",
    "AutoCompactTracking",
    "AUTO_COMPACT_BUFFER",
    "MAX_CONSECUTIVE_FAILURES",
]
