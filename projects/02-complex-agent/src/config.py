"""Configuration — loaded once at startup from env vars (CCC_ prefix) + .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


def _find_env_file() -> str:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".env").exists():
            return str(parent / ".env")
    return ".env"


class Config(BaseSettings):
    api_key: str = ""
    api_base: str = "https://api.anthropic.com"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16_384
    provider: Literal["anthropic", "openai", "compatible"] = "anthropic"
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = "gpt-4o"
    project_root: str = "."
    debug_log: bool = False

    model_config = {"env_prefix": "CCC_", "env_file": _find_env_file(), "env_file_encoding": "utf-8"}

    @property
    def effective_model(self) -> str:
        return f"openai/{self.openai_model}" if self.provider == "openai" else f"anthropic/{self.model}"

    @property
    def effective_api_key(self) -> str:
        return self.openai_api_key if self.provider == "openai" else self.api_key

    @property
    def effective_api_base(self) -> str | None:
        if self.provider == "openai":
            return self.openai_api_base or None
        return self.api_base or None

    @field_validator("project_root")
    @classmethod
    def _resolve_root(cls, v: str) -> str:
        p = Path(v).resolve()
        if not p.is_dir():
            raise ValueError(f"project_root is not a directory: {p}")
        return str(p)

    def validate_startup(self) -> None:
        if not self.effective_api_key:
            key = "CCC_OPENAI_API_KEY" if self.provider == "openai" else "CCC_API_KEY"
            raise ValueError(f"Missing required: {key}")
