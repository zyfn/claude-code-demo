# CCC — Claude Code Clone

A Python reimplementation of Claude Code's core architecture: AsyncGenerator-based ReAct loop, context compaction pipeline, unified tool executor, and hook system.

## Architecture

```
src/
├── main.py              # Entry point
├── repl.py              # Interactive REPL — holds messages, assembles deps
├── query.py             # Core AsyncGenerator ReAct loop
├── planning.py           # TodoManager + stateless reminder
├── system_prompt.py     # Static prompt template
├── config.py            # Pydantic settings (env vars)
├── context.py            # Environment采集 (git, CLAUDE.md, date)
├── types.py             # Shared types (Event, QueryDeps, compaction interfaces)
├── hooks.py             # HookRegistry + YAML config
├── ui.py                # Rich TUI renderer
├── api/                 # LiteLLM client + retry
├── tools/               # Tool protocol, executor, registry, impl/
│   └── impl/            # bash, file, grep, todo, subagent
├── compact/             # budget, micro, auto compaction stages
└── agents/             # Built-in agent definitions
```

## Key Features

- **ReAct Loop** — Pure AsyncGenerator, no agent class; repl.py holds messages and calls query()
- **Context Compaction** — Three-stage pipeline: budget → micro → auto_compact
- **Tool Executor** — Two-phase (permission + concurrent execution), supports hooks
- **Hook System** — Unified registry, code + YAML config, event-based dispatch
- **TodoWrite** — Full-replacement todo model with stateless reminder (5+ turns no todo_write → reminder)
- **Subagent** — AgentTool calls query() with isolated messages and executor

## Quick Start

```bash
source .venv/bin/activate
pip install -e .
python -m src.main
```

## Tech Stack

- Python 3.13+ / asyncio
- LiteLLM ( Anthropic + OpenAI backends)
- Rich (TUI)
- PyYAML (hooks config)
