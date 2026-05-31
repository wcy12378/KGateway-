from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # ── LLM Provider ───────────────────────────────────────────
    LLM_PROVIDER: str = Field(default="openai", description="'openai' or 'anthropic'")

    # OpenAI
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    OPENAI_API_BASE: Optional[str] = Field(default=None, description="Custom OpenAI-compatible base URL")

    # Anthropic (Xiaomi MiMo Pro etc.)
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    ANTHROPIC_BASE_URL: Optional[str] = Field(default=None, description="Anthropic-compatible base URL")

    # Model
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="Model identifier")

    # ── Qdrant ─────────────────────────────────────────────────
    QDRANT_URL: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    QDRANT_COLLECTION: str = Field(default="adaptive_rag", description="Collection name")
    QDRANT_API_KEY: Optional[str] = Field(default=None, description="Qdrant API key")

    # ── Retrieval ──────────────────────────────────────────────
    TOP_K: int = Field(default=4, description="Number of documents to retrieve")
    SCORE_THRESHOLD: float = Field(default=0.5, description="Minimum similarity score")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
