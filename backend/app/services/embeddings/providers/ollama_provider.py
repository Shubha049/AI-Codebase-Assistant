"""
Ollama embeddings provider via its real local HTTP API
(POST {OLLAMA_URL}/api/embeddings).

NOT VERIFIED END-TO-END in the environment this was built in: there is no
Ollama binary installed and no local Ollama server running in this
sandbox (confirmed: `which ollama` found nothing, and a request to
http://localhost:11434 got no response). The code below is written
against Ollama's real, documented request/response shape and should work
as-is against a real running Ollama instance — set OLLAMA_URL to point at
it (default http://localhost:11434) to use EMBEDDING_PROVIDER=ollama.

Unlike OpenAI/local, Ollama's embedding dimension genuinely depends on
whichever model the user has pulled (`ollama pull <model>`) — there's no
fixed lookup table that could be correct in general, so dimension is
determined by embedding a short probe string on first use rather than
guessed.
"""
from __future__ import annotations

import httpx

from app.services.embeddings.base import EmbeddingError, EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, model_name: str = "nomic-embed-text"):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._dimension: int | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            probe = self.embed_batch(["dimension probe"])
            self._dimension = len(probe[0])
        return self._dimension

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            with httpx.Client(timeout=60.0) as client:
                for text in texts:
                    response = client.post(
                        f"{self._base_url}/api/embeddings",
                        json={"model": self._model_name, "prompt": text},
                    )
                    response.raise_for_status()
                    data = response.json()
                    vectors.append(data["embedding"])
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"Ollama API returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"Could not reach Ollama at {self._base_url}: {exc}"
            ) from exc
        except (KeyError, ValueError) as exc:
            raise EmbeddingError(f"Unexpected Ollama response shape: {exc}") from exc

        return vectors
