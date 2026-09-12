"""
Phase 4 embedding pipeline: turns each repository's chunks into vectors
via the configured EmbeddingProvider and stores them in Qdrant with full
payload metadata.

Incremental indexing: a chunk is skipped if it already has `embedded_at`
set AND its `embedding_model` matches the CURRENTLY configured provider's
model — so a provider/model switch correctly triggers re-embedding even
though nothing about the chunk's content changed.

Duplicate chunks (Chunk.is_duplicate=True) still get their OWN Qdrant
point — with their own file/line/id metadata, so a duplicate living in a
DIFFERENT file is still independently searchable and citable — but reuse
the canonical chunk's already-computed vector instead of calling the
provider a second time for byte-identical content. (Earlier version
excluded duplicates from Qdrant entirely, which silently made any
duplicate's file/location unreachable via search even though its own
docstring claimed otherwise — found by tracing the actual query filters
against the doc comment, not assumed correct because it was well-written.)

Runs chained immediately after chunk generation — see
chunk_generation_pipeline.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from qdrant_client.models import PointStruct

from app.config import get_settings
from app.db.models import Chunk, IndexingJob, JobStage, JobStatus, Repository, RepoStatus
from app.db.session import SessionLocal
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.factory import build_embedding_provider
from app.services.embeddings.retry import embed_batch_with_retry
from app.services.vectorstore.qdrant_store import (
    collection_name_for_repo,
    collection_info,
    delete_collection,
    delete_points,
    ensure_collection,
    get_qdrant_client,
    list_point_ids,
    upsert_chunks,
)

logger = logging.getLogger(__name__)


def run_embedding_pipeline(repository_id: str, force: bool = False) -> None:
    db = SessionLocal()
    job = IndexingJob(repository_id=repository_id, stage=JobStage.EMBEDDING, status=JobStatus.RUNNING)
    db.add(job)
    db.commit()

    try:
        repo = db.get(Repository, repository_id)
        if repo is None:
            logger.error("run_embedding_pipeline: repository %s not found", repository_id)
            return

        repo.status = RepoStatus.INDEXING
        db.commit()

        settings = get_settings()
        provider = build_embedding_provider(settings)
        client = get_qdrant_client(settings)
        collection = collection_name_for_repo(repository_id, settings.qdrant_collection_prefix)

        if force:
            delete_collection(client, collection)
            db.query(Chunk).filter(Chunk.repository_id == repository_id).update(
                {"embedded_at": None, "embedding_model": None}, synchronize_session=False,
            )
            db.commit()

        ensure_collection(client, collection, provider.dimension)

        # Orphan cleanup considers ALL chunks now (duplicates included —
        # they have real points too, see module docstring above).
        if not force:
            valid_ids = {
                row.id for row in
                db.query(Chunk.id).filter(Chunk.repository_id == repository_id)
            }
            existing_point_ids = list_point_ids(client, collection)
            orphaned_ids = list(existing_point_ids - valid_ids)
            if orphaned_ids:
                delete_points(client, collection, orphaned_ids)
                logger.info(
                    "Removed %d orphaned vector(s) from repo %s's collection.",
                    len(orphaned_ids), repository_id,
                )
        else:
            orphaned_ids = []

        base_query = db.query(Chunk).filter(Chunk.repository_id == repository_id)
        total_eligible = base_query.count()
        chunks_to_process = base_query.filter(
            (Chunk.embedded_at.is_(None)) | (Chunk.embedding_model != provider.model_name)
        ).all()
        skipped_already_embedded = total_eligible - len(chunks_to_process)

        canonical_batch = [c for c in chunks_to_process if not c.is_duplicate]
        duplicate_batch = [c for c in chunks_to_process if c.is_duplicate]

        total = len(chunks_to_process) or 1
        batch_size = max(1, settings.embedding_batch_size)
        embedded_count = 0
        failed_count = 0
        vector_by_content_hash: dict[str, list[float]] = {}

        # --- Pass 1: real provider calls, canonical (non-duplicate) chunks only ---
        for batch_start in range(0, len(canonical_batch), batch_size):
            batch = canonical_batch[batch_start:batch_start + batch_size]
            texts = [c.content for c in batch]

            try:
                vectors = embed_batch_with_retry(provider, texts, settings.embedding_max_retries)
            except EmbeddingError as exc:
                logger.error(
                    "Embedding batch failed permanently for repo %s (chunks %d-%d): %s",
                    repository_id, batch_start, batch_start + len(batch), exc,
                )
                failed_count += len(batch)
                job.progress_percent = int((batch_start + len(batch)) / total * 90)
                continue

            points = [_build_point(c, vec, repository_id, repo.name) for c, vec in zip(batch, vectors)]
            upsert_chunks(client, collection, points)

            now = datetime.now(timezone.utc)
            for c, vec in zip(batch, vectors):
                c.embedded_at = now
                c.embedding_model = provider.model_name
                vector_by_content_hash[c.content_hash] = vec
            embedded_count += len(batch)
            job.progress_percent = int((batch_start + len(batch)) / total * 90)
            db.commit()

        # --- Pass 2: duplicates — reuse a vector, never call the provider again ---
        dup_points: list[PointStruct] = []
        dup_reembedded = 0
        for c in duplicate_batch:
            vec = vector_by_content_hash.get(c.content_hash)
            if vec is None:
                vec = _fetch_existing_vector_for_content_hash(
                    db, client, collection, repository_id, c.content_hash,
                )
            if vec is None:
                # No canonical vector available anywhere (edge case — e.g.
                # canonical itself failed to embed this run). Fall back to
                # a real, direct embed for this one chunk rather than
                # leaving it permanently unindexed.
                try:
                    vec = embed_batch_with_retry(provider, [c.content], settings.embedding_max_retries)[0]
                    dup_reembedded += 1
                except EmbeddingError as exc:
                    logger.error("Fallback embed failed for duplicate chunk %s: %s", c.id, exc)
                    failed_count += 1
                    continue
            vector_by_content_hash.setdefault(c.content_hash, vec)
            dup_points.append(_build_point(c, vec, repository_id, repo.name))
            c.embedded_at = datetime.now(timezone.utc)
            c.embedding_model = provider.model_name
            embedded_count += 1

        if dup_points:
            upsert_chunks(client, collection, dup_points)
            db.commit()
        job.progress_percent = 95

        info = collection_info(client, collection)
        repo.vector_count = info["points_count"] if info else 0
        repo.embedding_provider = provider.provider_name
        repo.embedding_model = provider.model_name
        repo.embedding_dimension = provider.dimension
        repo.indexed_at = datetime.now(timezone.utc)
        if failed_count > 0 and embedded_count == 0 and len(chunks_to_process) > 0:
            repo.status = RepoStatus.FAILED
            repo.error_message = f"Embedding failed for all {failed_count} chunks."
            job.status = JobStatus.FAILED
        else:
            repo.status = RepoStatus.READY
            job.status = JobStatus.COMPLETED

        job.progress_percent = 100
        job.message = (
            f"Embedded {embedded_count}/{len(chunks_to_process)} chunks "
            f"({failed_count} failed, {skipped_already_embedded} already embedded and skipped, "
            f"{dup_reembedded} duplicates needed a direct fallback embed, "
            f"{len(orphaned_ids)} orphaned vectors removed) "
            f"via {provider.provider_name}/{provider.model_name}. "
            f"Collection now has {repo.vector_count} vectors."
        )
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Embedding pipeline completed for repo %s: %s", repository_id, job.message)

    except Exception as exc:  # noqa: BLE001 - top-level pipeline guard
        logger.exception("Embedding pipeline failed for repo %s", repository_id)
        db.rollback()
        job.status = JobStatus.FAILED
        job.message = str(exc)
        repo = db.get(Repository, repository_id)
        if repo is not None:
            repo.status = RepoStatus.FAILED
            repo.error_message = f"Embedding pipeline failed: {exc}"
        db.commit()
    finally:
        db.close()


def _build_point(chunk: Chunk, vector: list[float], repository_id: str, repository_name: str) -> PointStruct:
    return PointStruct(
        id=chunk.id,
        vector=vector,
        payload={
            "repository_id": repository_id,
            "repository_name": repository_name,
            "language": chunk.language,
            "file_path": chunk.file_path,
            "module": chunk.file_path.rsplit(".", 1)[0].replace("/", "."),
            "class_name": chunk.parent_symbol_name,
            "function_name": chunk.symbol_name,
            "chunk_id": chunk.id,
            "chunk_type": chunk.chunk_type.value,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content_hash": chunk.content_hash,
            "is_duplicate": chunk.is_duplicate,
        },
    )


def _fetch_existing_vector_for_content_hash(
    db, client, collection: str, repository_id: str, content_hash: str,
) -> list[float] | None:
    """
    A duplicate's canonical may have been embedded in a PREVIOUS run (not
    this one), so its vector isn't in this run's in-memory cache. Look up
    any already-embedded chunk sharing the same content_hash and fetch its
    real vector back from Qdrant to reuse.
    """
    canonical = (
        db.query(Chunk)
        .filter(
            Chunk.repository_id == repository_id,
            Chunk.content_hash == content_hash,
            Chunk.embedded_at.isnot(None),
        )
        .first()
    )
    if canonical is None:
        return None
    records = client.retrieve(collection_name=collection, ids=[canonical.id], with_vectors=True)
    if not records:
        return None
    return records[0].vector
