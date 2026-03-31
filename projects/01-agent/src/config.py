"""Configuration management."""

from pydantic_settings import BaseSettings
from pathlib import Path


def _find_env_file() -> str:
    """Walk up from this file to find .env at the monorepo root."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".env").exists():
            return str(parent / ".env")
    return ".env"


class Settings(BaseSettings):
    # LLM Backend
    api_key: str = ""
    api_base: str = "https://api.anthropic.com"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192

    # Provider: anthropic | openai | compatible
    provider: str = "anthropic"

    # For OpenAI-compatible providers
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = "gpt-4o"

    # Project
    project_root: str = "."

    # TUI
    theme: str = "dark"
    show_thinking: bool = True

    # Debug
    debug_log: bool = False  # Save raw request/response to debug/ directory

    class Config:
        env_prefix = "CCC_"
        env_file = _find_env_file()
        env_file_encoding = "utf-8"


settings = Settings()
