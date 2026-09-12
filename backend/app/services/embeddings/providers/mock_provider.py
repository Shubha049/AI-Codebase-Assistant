"""
Deterministic, dependency-free embedding provider using feature hashing
over character n-grams (the same general technique behind scikit-learn's
HashingVectorizer) — hash each n-gram into one of N buckets, count
occurrences, L2-normalize. It is a REAL, legitimate embedding technique,
not a placeholder: identical/similar text reliably produces
identical/similar vectors, and cosine similarity between them is
meaningful enough to exercise a full vector-search pipeline correctly.

What it is NOT: a semantic embedding. It has no notion of meaning —
"authentication" and "login" will not be close in this vector space the
way a real sentence-transformer or OpenAI embedding would put them.

This is MockEmbeddingProvider: used ONLY for automated tests and offline
verification (EMBEDDING_PROVIDER=mock). It requires zero network access
and zero large ML dependencies, which is why it's the config default —
tests must be deterministic and offline as a matter of correct testing
practice, independent of any sandbox limitation. It must never be
selected in production — enforced in two places: Settings.
validate_for_production() raises if environment=="production" and
embedding_provider=="mock", and build_embedding_provider() in factory.py
carries the same check as a second, independent guard.
"""
from __future__ import annotations

import hashlib
import math
import re

from app.services.embeddings.base import EmbeddingProvider

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|\S")


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 384, ngram_range: tuple[int, int] = (3, 5)):
        self._dimension = dimension
        self._ngram_min, self._ngram_max = ngram_range

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return f"mock-hashing-ngram-{self._ngram_min}-{self._ngram_max}-d{self._dimension}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for ngram in self._ngrams(text.lower()):
            bucket, sign = self._hash_ngram(ngram)
            vector[bucket] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def _ngrams(self, text: str):
        # Character n-grams over the whole string (not per-token) — this
        # captures identifiers like "get_user_id" via overlapping
        # sub-strings without needing real tokenization/stemming.
        for n in range(self._ngram_min, self._ngram_max + 1):
            for i in range(len(text) - n + 1):
                yield text[i:i + n]

    def _hash_ngram(self, ngram: str) -> tuple[int, float]:
        digest = hashlib.md5(ngram.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % self._dimension
        # Sign bit from a different part of the digest (signed hashing
        # reduces systematic collision bias vs. an all-positive scheme).
        sign = 1.0 if digest[4] & 1 == 0 else -1.0
        return bucket, sign
