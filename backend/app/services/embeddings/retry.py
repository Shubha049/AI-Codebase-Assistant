"""
Wraps EmbeddingProvider.embed_batch with retry/backoff for transient
failures (network blips, rate limits, etc.). Kept separate from the
providers themselves so every provider gets identical retry behavior
without duplicating it.
"""
from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.services.embeddings.base import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)


def embed_batch_with_retry(
    provider: EmbeddingProvider, texts: list[str], max_retries: int
) -> list[list[float]]:
    @retry(
        retry=retry_if_exception_type(EmbeddingError),
        stop=stop_after_attempt(max(1, max_retries)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    def _attempt() -> list[list[float]]:
        return provider.embed_batch(texts)

    try:
        return _attempt()
    except EmbeddingError as exc:
        logger.error(
            "Embedding batch of %d texts failed after %d attempt(s) via %s: %s",
            len(texts), max_retries, provider.provider_name, exc,
        )
        raise
