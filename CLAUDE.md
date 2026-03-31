# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This is a monorepo containing multiple independent sub-projects under `projects/`. Each sub-project has its own `pyproject.toml`, `src/`, and `tests/`.

| Sub-project | Path | Description |
|-------------|------|-------------|
| 01-agent | `projects/01-agent/` | ReAct agent loop with Anthropic + OpenAI backends |
| 02-complex-agent | `projects/02-complex-agent/` | *(coming soon)* |

## Key Commands

```bash
# Work on a sub-project
cd projects/01-agent
pip install -e .
ccc                    # run the CLI
ruff check .           # lint
pytest                 # run tests
```

## Adding a New Sub-project

1. Create `projects/NN-name/` with `src/`, `tests/`, `pyproject.toml`
2. Update this file and the root `README.md` to include it
