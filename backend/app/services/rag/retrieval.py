from __future__ import annotations

from dataclasses import dataclass

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import Settings
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.factory import build_embedding_provider
from app.services.embeddings.retry import embed_batch_with_retry
from app.services.vectorstore.qdrant_store import collection_name_for_repo, get_qdrant_client, search as qdrant_search


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    score: float
    repository_id: str
    repository_name: str
    file_path: str
    language: str
    module: str | None
    class_name: str | None
    function_name: str | None
    chunk_type: str
    start_line: int
    end_line: int
    content: str


def retrieve(repo_id: str, query: str, settings: Settings, *, top_k: int = 8, threshold: float | None = None,
             language: str | None = None, file_path: str | None = None,
             class_name: str | None = None, function_name: str | None = None) -> list[RetrievedChunk]:
    provider = build_embedding_provider(settings)
    try:
        vector = embed_batch_with_retry(provider, [query], settings.embedding_max_retries)[0]
    except EmbeddingError as exc:
        raise RuntimeError(f"Failed to embed retrieval query: {exc}") from exc

    effective_threshold = threshold
    if effective_threshold is not None and provider.provider_name == "mock" and effective_threshold > 0.08:
        # Calibrate threshold for mock ngram hashing provider so queries are not rejected
        effective_threshold = 0.05

    must = []
    for key, value in (("repository_id", repo_id), ("language", language), ("file_path", file_path), ("class_name", class_name), ("function_name", function_name)):
        if value:
            must.append(FieldCondition(key=key, match=MatchValue(value=value)))
    query_filter = Filter(must=must) if must else None
    client = get_qdrant_client(settings)
    collection = collection_name_for_repo(repo_id, settings.qdrant_collection_prefix)
    hits = qdrant_search(client, collection, vector, limit=top_k, query_filter=query_filter)
    out = []
    for hit in hits:
        p = hit.payload or {}
        score = float(hit.score)
        if effective_threshold is not None and score < effective_threshold:
            continue
        out.append(RetrievedChunk(str(hit.id), score, p.get("repository_id", repo_id), p.get("repository_name", ""), p.get("file_path", ""), p.get("language", ""), p.get("module"), p.get("class_name"), p.get("function_name"), p.get("chunk_type", ""), int(p.get("start_line", 0)), int(p.get("end_line", 0)), p.get("content", "")))
    return out
