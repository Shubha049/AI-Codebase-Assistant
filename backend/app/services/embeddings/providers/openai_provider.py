"""
OpenAI embeddings provider via direct HTTPS calls to the real /v1/embeddings
endpoint (no `openai` SDK dependency needed for this).

NOT VERIFIED END-TO-END in the environment this was built in: this
sandbox's network egress is restricted to a fixed allow-list of domains
(package registries, GitHub) that does not include api.openai.com —
confirmed directly: a request to it returned HTTP 403 from the egress
proxy, before any API key or request body is even considered. The code
below is written against OpenAI's real, documented request/response
shape and should work as-is with a valid OPENAI_API_KEY in an environment
that can reach api.openai.com.
"""
from __future__ import annotations

import httpx

from app.services.embeddings.base import EmbeddingError, EmbeddingProvider

_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small"):
        if not api_key:
            raise EmbeddingError("OPENAI_API_KEY is not set.")
        self._api_key = api_key
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._model_name not in _MODEL_DIMENSIONS:
            raise EmbeddingError(
                f"Unknown OpenAI embedding model '{self._model_name}'; "
                f"known models: {sorted(_MODEL_DIMENSIONS)}"
            )
        return _MODEL_DIMENSIONS[self._model_name]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model_name, "input": texts},
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"OpenAI API returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"OpenAI API request failed: {exc}") from exc

        data = response.json()
        items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]
