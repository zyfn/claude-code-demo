"""Skills package — 两层注入设计.

Layer 1: format_skills_for_system_prompt() → 系统提示中的简短描述
Layer 2: get_skill_content(name) → 模型调用 load_skill 时返回完整内容
"""

from .loader import (
    get_skill_loader,
    format_skills_for_system_prompt,
    get_skill_content,
)
from .types import (
    ToolUseContext,
)

__all__ = [
    "get_skill_loader",
    "format_skills_for_system_prompt",
    "get_skill_content",
    "ToolUseContext",
]
