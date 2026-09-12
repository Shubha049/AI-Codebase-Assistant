"""
Thin wrapper around qdrant-client. Supports both:
  - Embedded mode: QDRANT_URL=":memory:" (ephemeral, per-process) or a
    local filesystem path (persistent, no server) — a real mode the
    qdrant-client library ships, not a mock.
  - Server mode: QDRANT_URL="http://host:port" for a real Qdrant service
    (e.g. the docker-compose Qdrant container from Phase 0's plan).

One collection per repository (named f"{prefix}_{repository_id}") rather
than one shared collection filtered by repository_id — this makes
"delete a repository's vectors" and "re-index a repository" both a clean
single-collection operation instead of a filtered bulk-delete across a
shared index.
"""
import logging
import re
import threading

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None
_client_url: str | None = None
_client_lock = threading.Lock()


def get_qdrant_client(settings: Settings | None = None) -> QdrantClient:
    """
    Process-wide thread-safe singleton, rebuilt if QDRANT_URL changes (relevant
    for tests that override settings). Real embedded storage for ":memory:"
    or a local path — not a mock.
    """
    global _client, _client_url
    settings = settings or get_settings()
    with _client_lock:
        if _client is None or _client_url != settings.qdrant_url:
            url = settings.qdrant_url
            if url == ":memory:":
                _client = QdrantClient(":memory:")
            elif url.startswith("http://") or url.startswith("https://"):
                _client = QdrantClient(url=url)
            else:
                import time
                last_exc = None
                for attempt in range(5):
                    try:
                        _client = QdrantClient(path=url)
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        logger.warning(
                            "Transient lock contention on Qdrant local storage path '%s' (attempt %d/5): %s",
                            url,
                            attempt + 1,
                            exc,
                        )
                        time.sleep(0.5 * (attempt + 1))
                if last_exc is not None or _client is None:
                    err_msg = (
                        f"CRITICAL: Failed to acquire local Qdrant storage lock on '{url}' after 5 retries. "
                        f"Another process is holding the file lock. To prevent vector data loss, operation aborted. "
                        f"For concurrent / multi-process execution, configure QDRANT_URL to a standalone Qdrant server "
                        f"(e.g. QDRANT_URL=http://localhost:6333 via Docker) instead of local embedded file mode."
                    )
                    logger.critical(err_msg)
                    raise RuntimeError(err_msg) from last_exc
            _client_url = url
    return _client


def collection_name_for_repo(repository_id: str, prefix: str) -> str:
    # Qdrant collection names are fairly permissive, but keep this
    # predictable and filesystem-safe regardless (matters for path-mode
    # embedded storage, where the collection name becomes part of a path).
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", repository_id)
    return f"{prefix}_{safe_id}"


def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upsert_chunks(client: QdrantClient, collection: str, points: list[PointStruct]) -> None:
    if not points:
        return
    client.upsert(collection_name=collection, points=points, wait=True)


def delete_points(client: QdrantClient, collection: str, point_ids: list[str]) -> None:
    if not point_ids:
        return
    if not client.collection_exists(collection):
        return
    client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=point_ids),
        wait=True,
    )


def delete_collection(client: QdrantClient, collection: str) -> None:
    if client.collection_exists(collection):
        client.delete_collection(collection)


def search(
    client: QdrantClient, collection: str, query_vector: list[float], limit: int = 10, query_filter: Filter | None = None,
):
    if not client.collection_exists(collection):
        return []
    return client.query_points(
        collection_name=collection, query=query_vector, query_filter=query_filter, limit=limit, with_payload=True,
    ).points


def collection_info(client: QdrantClient, collection: str) -> dict | None:
    if not client.collection_exists(collection):
        return None
    info = client.get_collection(collection)
    return {
        "points_count": info.points_count,
        "vectors_count": info.vectors_count,
        "status": info.status.value if hasattr(info.status, "value") else str(info.status),
        "vector_size": info.config.params.vectors.size,
    }


def list_point_ids(client: QdrantClient, collection: str) -> set[str]:
    """
    All point IDs currently in the collection. Used to find and remove
    ORPHANED vectors — points left behind in Qdrant after their source
    Chunk row was deleted or regenerated with a new ID (e.g. Phase 3
    re-chunking a changed file creates fresh chunk IDs; nothing about
    that process knows to also clean up the old vector, since chunking
    has no Qdrant dependency by design — this is Phase 4's job instead).
    """
    if not client.collection_exists(collection):
        return set()
    ids: set[str] = set()
    next_offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection, limit=1000, offset=next_offset,
            with_payload=False, with_vectors=False,
        )
        ids.update(str(p.id) for p in points)
        if next_offset is None:
            break
    return ids


def health_check(client: QdrantClient) -> bool:
    try:
        client.get_collections()
        return True
    except Exception:  # noqa: BLE001 - health check: any failure = unhealthy
        return False
