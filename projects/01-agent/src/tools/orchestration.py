"""Tool orchestration — partition tool calls by concurrency safety.

partition_tool_calls() groups tools into batches:
- isConcurrencySafe tools → concurrent batch (up to MAX_CONCURRENT)
- Non-safe tools → serial batch (one at a time)
"""

from dataclasses import dataclass

from src.tools.base import BaseTool


MAX_CONCURRENT = 10


@dataclass
class ToolCall:
    """A single tool call to execute."""
    name: str
    params: dict
    tool_call_id: str


@dataclass
class Batch:
    """A batch of tool calls — either concurrent or serial."""
    concurrent: bool
    calls: list[ToolCall]


def partition_tool_calls(calls: list[ToolCall], tools: dict[str, BaseTool]) -> list[Batch]:
    """Partition tool calls into batches based on concurrency safety.

    Safe tools are grouped into concurrent batches (max MAX_CONCURRENT per batch).
    Unsafe tools each get their own serial batch.
    """
    batches: list[Batch] = []

    for call in calls:
        tool = tools.get(call.name)
        is_safe = False
        try:
            is_safe = tool.is_concurrency_safe(**call.params) if tool else False
        except Exception:
            is_safe = False  # Conservative

        last = batches[-1] if batches else None
        if is_safe and last and last.concurrent:
            last.calls.append(call)
        else:
            batches.append(Batch(concurrent=is_safe, calls=[call]))

    return batches
