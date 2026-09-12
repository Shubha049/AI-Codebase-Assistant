"""
Application configuration.

Single source of truth for all environment-driven settings. Uses
pydantic-settings so that:
  - types are enforced (a bad int/bool in .env fails at startup, not at
    first use three requests later)
  - there is exactly one name for each setting (no more `.env` vs
    `.env.example` vs "what the code actually reads" drifting apart)
  - sensible defaults exist so the app runs with zero configuration for
    local development, but nothing is silently wrong in production
    because required-for-production values are validated in `validate_for_production()`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "AI Codebase Assistant"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    # --- Server ---
    host: str = "0.0.0.0"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:5176",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://127.0.0.1:5176",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # --- Database ---
    # SQLite by default so `pip install && run` works with zero setup.
    # Point DATABASE_URL at Postgres for production.
    database_url: str = "sqlite:///./data/aica.db"

    # --- Storage ---
    data_dir: Path = Path("./data")
    upload_tmp_dir: Path = Path("./data/tmp")
    repo_storage_dir: Path = Path("./data/repositories")

    # --- Upload limits ---
    max_upload_size_mb: int = 50
    max_files_per_repo: int = 5000

    # --- Analyzable file extensions (scanning stage) ---
    analyzable_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb",
            ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".rs", ".swift",
            ".kt", ".scala", ".sql", ".html", ".css", ".json", ".yaml",
            ".yml", ".md",
        ]
    )

    # --- Directories always skipped while scanning ---
    skip_dir_names: list[str] = Field(
        default_factory=lambda: [
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".next", ".pytest_cache", ".mypy_cache",
            "coverage", ".idea", ".vscode",
        ]
    )

    # --- Production/authentication ---
    auth_secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 60
    allow_registration: bool = True
    trusted_proxy_count: int = 0

    # --- Future phases (present now so config never drifts later) ---
    embedding_provider: Literal["local", "openai", "ollama", "mock"] = "mock"
    llm_provider: Literal["none", "openai", "ollama", "mock"] = "mock"
    llm_api_key: str | None = None
    llm_model_name: str = "qwen2.5:0.5b"
    llm_timeout_seconds: int = 180
    llm_max_tokens: int = 250
    ollama_keep_alive: str = "30m"
    qdrant_url: str = "./data/qdrant"

    # --- Phase 4: embeddings & vector storage ---
    # Default provider is "mock" (MockEmbeddingProvider — see
    # providers/mock_provider.py) — zero setup, zero network, matches
    # this project's "runs out of the box" philosophy from Phase 1, and
    # is what automated tests use. It must NEVER be used in production —
    # enforced below in validate_for_production() and independently in
    # the provider factory. Switch to "local"/"openai"/"ollama" for real
    # semantic embeddings once the relevant dependency/API key/server is
    # available.
    openai_api_key: str | None = None
    ollama_url: str = "http://localhost:11434"
    embedding_model: str | None = None  # None = each provider's own default
    embedding_batch_size: int = 32
    embedding_max_retries: int = 3
    qdrant_collection_prefix: str = "aica_chunks"

    # --- Chunking (Phase 3) ---
    # Token counts here are an APPROXIMATION (chars/4, a common rule of
    # thumb for English/code text), not a real tokenizer — no embedding
    # provider has been chosen yet, so there's no model-specific tokenizer
    # to match. Documented as approximate everywhere it's surfaced.
    chunk_max_tokens: int = 400
    chunk_overlap_ratio: float = 0.15

    @field_validator("data_dir", "upload_tmp_dir", "repo_storage_dir", mode="after")
    @classmethod
    def _ensure_dir_exists(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    def validate_for_production(self) -> None:
        """Call at startup when environment == 'production'. Raises with a
        clear message instead of letting the app boot half-configured."""
        problems: list[str] = []
        if self.auth_secret_key == "dev-only-change-me" or len(self.auth_secret_key) < 32:
            problems.append("AUTH_SECRET_KEY must be a strong random value of at least 32 characters in production.")
        if self.allow_registration:
            problems.append("ALLOW_REGISTRATION=true in production — disable public registration after creating initial accounts.")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS cannot contain * in production.")
        if self.database_url.startswith("sqlite"):
            problems.append(
                "DATABASE_URL is sqlite in production — set a real Postgres URL."
            )
        if self.llm_provider == "openai" and not self.llm_api_key:
            problems.append(
                "LLM_PROVIDER=openai but LLM_API_KEY is not set."
            )
        if self.llm_provider == "mock":
            problems.append("LLM_PROVIDER=mock in production — MockLLMProvider is for tests/offline verification only.")
        if self.embedding_provider == "mock":
            problems.append(
                "EMBEDDING_PROVIDER=mock in production — MockEmbeddingProvider "
                "produces non-semantic vectors and is for tests/offline "
                "verification only. Set it to 'local', 'openai', or 'ollama'."
            )
        if self.embedding_provider == "openai" and not self.openai_api_key:
            problems.append(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set."
            )
        if problems:
            raise RuntimeError(
                "Refusing to start in production with invalid config:\n- "
                + "\n- ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
