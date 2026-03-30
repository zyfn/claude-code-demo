# Claude Code Clone (CCC)

A terminal AI coding assistant inspired by Claude Code, built from scratch in Python.

## Features

- 🤖 **Agent Loop** — ReAct-style think-act cycle with tool use
- 🔧 **Built-in Tools** — Read/write/edit files, bash execution, grep search
- 💬 **Multi-provider** — Anthropic & OpenAI-compatible API backends
- 🖥️ **Terminal UI** — Rich-based interactive interface with markdown rendering
- 📁 **Project Context** — Auto-detects file tree and git status

## Quick Start

```bash
# Install dependencies
pip install -e .

# Configure (set your API key)
export CCC_API_KEY="your-api-key"
export CCC_MODEL="claude-sonnet-4-20250514"  # or any model

# Or use OpenAI-compatible provider
export CCC_PROVIDER="openai"
export CCC_OPENAI_API_KEY="sk-..."
export CCC_OPENAI_MODEL="gpt-4o"

# Run
python -m src.main
```

## Architecture

```
src/
├── main.py              # Entry point
├── config.py            # Settings via pydantic-settings
├── agent/
│   └── loop.py          # ReAct agent loop
├── clients/
│   ├── base.py          # Abstract LLM client
│   ├── anthropic_client.py
│   └── openai_client.py
├── tools/
│   ├── base.py          # Tool interface
│   └── file_tools.py    # read_file, write_file, edit_file, bash, grep
├── tui/
│   └── interface.py     # Rich-based terminal UI
└── context/
    └── project.py       # Project awareness (file tree, git)
```

## Adding Tools

Create a new class inheriting from `BaseTool`:

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {"arg": {"type": "string", "description": "An argument"}}

    async def execute(self, arg: str) -> ToolResult:
        return ToolResult(f"Result: {arg}")
```

Then add it to the tools list in `main.py`.

## License

MIT
