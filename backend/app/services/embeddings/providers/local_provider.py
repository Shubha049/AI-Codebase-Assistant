"""
Local embedding provider via sentence-transformers.

NOT VERIFIED END-TO-END in the environment this was built in: loading a
model requires downloading weights from HuggingFace Hub at runtime, and
that domain is blocked by this sandbox's network egress rules (confirmed:
a direct request to huggingface.co returned HTTP 403). Separately,
`pip install sentence-transformers` pulls in torch, whose default PyPI
wheel drags in several GB of NVIDIA CUDA packages regardless of whether a
GPU is present — that alone exhausted this sandbox's disk on a real,
timed attempt (see README "Known limitations" for the exact commands and
errors). Both are environment constraints, not reasons to skip writing
this correctly: the code below is written against sentence-transformers'
real API and should work as-is in a normal environment with internet
access — install it with `pip install sentence-transformers` (see
requirements.txt) to enable EMBEDDING_PROVIDER=local.
"""
from __future__ import annotations

from app.services.embeddings.base import EmbeddingError, EmbeddingProvider

# Known output dimension per model — avoids having to load the model just
# to answer `.dimension` (needed up front to size the Qdrant collection).
_MODEL_DIMENSIONS = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "multi-qa-MiniLM-L6-cos-v1": 384,
}


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None  # lazy-loaded on first embed_batch call

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._model_name in _MODEL_DIMENSIONS:
            return _MODEL_DIMENSIONS[self._model_name]
        # Unknown model name — fall back to loading it to ask directly.
        self._ensure_loaded()
        return self._model.get_sentence_embedding_dimension()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers is not installed. Run "
                "`pip install sentence-transformers` (see requirements.txt "
                "comment) to use EMBEDDING_PROVIDER=local."
            ) from exc
        try:
            self._model = SentenceTransformer(self._model_name)
        except Exception as exc:  # noqa: BLE001 - network/download errors,
            # missing cache, etc. — surfaced as one clear EmbeddingError
            # rather than letting a raw huggingface_hub exception through.
            raise EmbeddingError(
                f"Failed to load local model '{self._model_name}': {exc}"
            ) from exc

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        try:
            embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            return embeddings.tolist()
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Local embedding batch failed: {exc}") from exc
