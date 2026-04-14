"""Tools package.

Importing this package triggers auto-registration of all tool subclasses
via BaseTool.__init_subclass__. Use get_all_tools() to retrieve the
complete registered tool pool.
"""

from src.tools.base import get_all_tools
from src.tools.impl.file import ReadFileTool, WriteFileTool, EditFileTool
from src.tools.impl.bash import BashTool
from src.tools.impl.grep import GrepTool
from src.tools.impl.subagent import SubAgentTool
from src.tools.impl.skill import LoadSkillTool

__all__ = [
    "get_all_tools",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "BashTool",
    "GrepTool",
    "SubAgentTool",
    "LoadSkillTool",
]
