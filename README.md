# CCC — Claude Code Clone

> A Python reimplementation of Claude Code's core architecture

![Python](https://img.shields.io/badge/python-3.13+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-experimental-orange.svg)

**CCC** reimplements Claude Code's soul in Python — AsyncGenerator ReAct loop, context compaction pipeline, unified tool executor, and a hook system that actually works.

---

## Architecture

```
src/
├── main.py              ──►  Entry point
├── repl.py              ──►  REPL — holds messages, assembles deps
├── query.py             ──►  AsyncGenerator ReAct loop
├── planning.py          ──►  TodoManager + stateless reminder
├── system_prompt.py     ──►  Static prompt template
├── config.py            ──►  Pydantic settings
├── context.py           ──►  Git, CLAUDE.md, date
├── types.py             ──►  Shared types & interfaces
├── hooks.py             ──►  HookRegistry + YAML config
├── ui.py                ──►  Rich TUI renderer
│
├── api/                 ──►  LiteLLM client + retry
├── compact/             ──►  budget → micro → auto_compact
├── tools/               ──►  Protocol, executor, registry
│   └── impl/            ──►  bash · file · grep · todo · subagent
└── agents/              ──►  Built-in agent definitions
```

---

## Core Features

| Feature | What it does |
|---------|-------------|
| **ReAct Loop** | Pure AsyncGenerator, no Agent class — `repl.py` owns messages, calls `query()` |
| **Compaction Pipeline** | 3-stage: `budget` → `micro` → `auto_compact` |
| **Tool Executor** | Two-phase: permission (sequential) + execution (concurrent) |
| **Hook System** | Unified registry, code + YAML config, event dispatch |
| **TodoWrite** | Full-replacement model — 5+ turns without `todo_write` triggers reminder |
| **Subagent** | `AgentTool` calls `query()` with isolated messages & executor |

---

## How It Works

```
User Input
    │
    ▼
┌─────────────────────────────────────────┐
│              repl.py                     │
│  ┌─────────────────────────────────────┐ │
│  │           query()                    │ │
│  │                                     │ │
│  │   ① Compaction (budget→micro→auto)   │ │
│  │   ② API Call (stream)               │ │
│  │   ③ Tool Executor (permission+exec) │ │
│  │   ④ Yield events → repl.py          │ │
│  └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
    │
    ▼
 TUI Output
```

---

## Quick Start

```bash
# Clone & enter
cd claude-code-demo

# Virtual environment
python -m venv .venv && source .venv/bin/activate

# Install
pip install -e .

# Run
python -m src.main
```

> **Tip:** Enable debug logs with `CCC_DEBUG_LOG=true python -m src.main`

---

## Tech Stack

<p>
  <img src="https://img.shields.io/badge/Python-3.13+-blue" alt="Python"/>
  <img src="https://img.shields.io/badge/LiteLLM-Anthropic%20%2B%20OpenAI-blueviolet" alt="LiteLLM"/>
  <img src="https://img.shields.io/badge/Rich-TUI-yellowgreen" alt="Rich"/>
  <img src="https://img.shields.io/badge/PyYAML-Hooks%20config-yellow" alt="PyYAML"/>
</p>

---

## Design Principles

1. **No Agent class** — The REPL holds state; `query()` is a pure function
2. **Events over返回值** — AsyncGenerator yields events, caller dispatches
3. **Hooks everywhere** — All side effects go through the hook system
4. **Compaction is compositional** — Add new stages by implementing `CompactionStage`
