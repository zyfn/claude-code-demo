"""Tool definitions and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class ToolResult:
    output: str
    is_error: bool = False


# Global tool registry — populated automatically when tool classes are imported.
_tool_registry: dict[str, type["BaseTool"]] = {}


def get_all_tools() -> list["BaseTool"]:
    """Instantiate and return all registered tools, sorted by name."""
    return [cls() for cls in sorted(_tool_registry.values(), key=lambda c: c.name)]


class BaseTool(ABC):
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    # Each key maps to an OpenAI-compatible parameter schema dict.
    # Mark optional params by adding "optional": True inside the schema dict.
    parameters: ClassVar[dict] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Auto-register subclasses that have a non-empty name
        if cls.name:
            _tool_registry[cls.name] = cls

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        ...

    def to_schema(self) -> dict:
        """Generate OpenAI-compatible tool schema."""
        properties = {}
        required = []
        for name, schema in self.parameters.items():
            # Strip the internal "optional" marker before sending to the API
            param_schema = {k: v for k, v in schema.items() if k != "optional"}
            properties[name] = param_schema
            if not schema.get("optional", False):
                required.append(name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
