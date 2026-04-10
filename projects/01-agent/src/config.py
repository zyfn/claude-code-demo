"""Configuration management with validation."""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from pathlib import Path
from typing import Literal


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
    provider: Literal["anthropic", "openai", "compatible"] = "anthropic"

    # For OpenAI-compatible providers
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = "gpt-4o"

    # Project
    project_root: str = "."

    # TUI
    theme: str = "dark"

    # Debug
    debug_log: bool = False  # Save raw request/response to debug/ directory

    class Config:
        env_prefix = "CCC_"
        env_file = _find_env_file()
        env_file_encoding = "utf-8"

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if v < 1 or v > 128000:
            raise ValueError("max_tokens must be between 1 and 128000")
        return v

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, v: str) -> str:
        p = Path(v).resolve()
        if not p.exists():
            raise ValueError(f"Project root does not exist: {p}")
        if not p.is_dir():
            raise ValueError(f"Project root is not a directory: {p}")
        return str(p)

    # Unified accessors — avoids scattered provider logic
    @property
    def effective_model(self) -> str:
        if self.provider == "openai":
            return f"openai/{self.openai_model}"
        return f"anthropic/{self.model}"

    @property
    def effective_api_key(self) -> str:
        if self.provider == "openai":
            return self.openai_api_key
        return self.api_key

    @property
    def effective_api_base(self) -> str | None:
        if self.provider == "openai":
            return self.openai_api_base or None
        return self.api_base or None

    def validate(self) -> None:
        """Validate configuration and raise early errors.
        
        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        errors = []
        
        # API key validation
        if not self.effective_api_key:
            key_name = "OPENAI_API_KEY" if self.provider == "openai" else "API_KEY"
            errors.append(f"Missing required environment variable: CCC_{key_name}")
        
        # Model name validation
        model = self.effective_model
        if not model or model in ("openai/", "anthropic/"):
            errors.append("Model name is not properly configured")
        
        # Provider-specific validation
        if self.provider == "openai" and not self.openai_model:
            errors.append("OpenAI provider requires openai_model to be set")
        
        if errors:
            raise ValueError("Configuration validation failed:\n  - " + "\n  - ".join(errors))


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get settings instance with validation."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def validate_settings() -> Settings:
    """Validate and return settings, failing fast on errors."""
    s = get_settings()
    s.validate()
    return s


settings = get_settings()
