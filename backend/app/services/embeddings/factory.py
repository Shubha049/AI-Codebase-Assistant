"""
Single place that turns config into a concrete EmbeddingProvider instance.
Nothing outside this module (and the providers themselves) should
reference a specific provider class.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.services.embeddings.base import EmbeddingError, EmbeddingProvider


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider

    if provider == "mock" and settings.environment == "production":
        # Second, independent guard against MockEmbeddingProvider ever
        # running in production — the first is Settings.
        # validate_for_production(), called at app startup. This one
        # fires even if that startup check were ever bypassed or this
        # function were called some other way.
        raise EmbeddingError(
            "EMBEDDING_PROVIDER=mock is not allowed when ENVIRONMENT=production. "
            "MockEmbeddingProvider produces non-semantic vectors and exists only "
            "for tests/offline verification."
        )

    if provider == "mock":
        from app.services.embeddings.providers.mock_provider import MockEmbeddingProvider
        return MockEmbeddingProvider()

    if provider == "local":
        from app.services.embeddings.providers.local_provider import LocalEmbeddingProvider
        model = settings.embedding_model or "all-MiniLM-L6-v2"
        return LocalEmbeddingProvider(model_name=model)

    if provider == "openai":
        from app.services.embeddings.providers.openai_provider import OpenAIEmbeddingProvider
        model = settings.embedding_model or "text-embedding-3-small"
        if not settings.openai_api_key:
            raise EmbeddingError(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set."
            )
        return OpenAIEmbeddingProvider(api_key=settings.openai_api_key, model_name=model)

    if provider == "ollama":
        from app.services.embeddings.providers.ollama_provider import OllamaEmbeddingProvider
        model = settings.embedding_model or "nomic-embed-text"
        return OllamaEmbeddingProvider(base_url=settings.ollama_url, model_name=model)

    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER: {provider!r}")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """
    Cached singleton for the app's actual runtime provider (so e.g. a
    local model isn't reloaded per request). Tests should NOT rely on
    this cache — they construct providers directly via
    build_embedding_provider(settings) so each test can use its own
    settings without cross-test contamination.
    """
    return build_embedding_provider(get_settings())
