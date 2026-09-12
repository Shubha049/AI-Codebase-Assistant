"""
Common interface every embedding provider implements. Selected entirely
through config (EMBEDDING_PROVIDER) — no provider-specific code anywhere
outside app/services/embeddings/providers/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """Raised by a provider when a batch genuinely fails (network error,
    API error, etc.) — caught and retried by the pipeline's retry wrapper,
    not by providers themselves."""


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifies the specific model in use, e.g.
        'all-MiniLM-L6-v2' or 'text-embedding-3-small'. Stored per-chunk
        so a model change (even with the same provider) correctly
        triggers re-embedding — see Chunk.embedding_model."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector size this provider/model produces. Used to create the
        Qdrant collection with the right size up front."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a batch of texts, returning one vector per input text, in
        the same order. Raises EmbeddingError on failure — callers (the
        embedding pipeline) are responsible for retry/backoff, not this
        method itself.
        """
        ...
