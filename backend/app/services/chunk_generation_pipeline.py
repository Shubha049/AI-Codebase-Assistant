"""
Phase 3 chunk generation: turns each analyzable file into semantic chunks
(via app.services.chunking.symbol_chunker) and persists them, with:

  - Incremental indexing: a file whose content hash matches its last
    recorded ChunkedFile hash is skipped entirely (not re-parsed, not
    re-chunked, its existing Chunk rows are left untouched).
  - Duplicate detection: computed as a REPO-WIDE pass after chunking, not
    incrementally per-file — simpler to reason about and impossible to
    get subtly wrong across re-runs. Every chunk's duplicate_of_chunk_id
    is reset and recomputed from the current full chunk set each run,
    which also self-heals any staleness from a previous partial run.

Runs as the next stage after analysis (JobStage.CHUNKING), chained from
run_analysis_pipeline — see analysis_pipeline.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Chunk,
    ChunkedFile,
    ChunkType,
    IndexingJob,
    JobStage,
    JobStatus,
    Repository,
    RepoStatus,
)
from app.db.session import SessionLocal
from app.services.chunking.hashing import hash_bytes, hash_content
from app.services.chunking.symbol_chunker import generate_chunks_for_file
from app.services.ingestion.scanner import scan_repository
from app.services.parsing.orchestrator import parse_file

logger = logging.getLogger(__name__)


def _safe_chunk_type(raw_type: str | ChunkType) -> ChunkType:
    if isinstance(raw_type, ChunkType):
        return raw_type
    try:
        return ChunkType(raw_type)
    except Exception:
        # Check if it matches a known synonym/mapping
        try:
            from app.services.chunking.symbol_chunker import map_symbol_to_chunk_type
            mapped = map_symbol_to_chunk_type(str(raw_type))
            return ChunkType(mapped)
        except Exception:
            logger.warning(
                "Unrecognized chunk type %r in candidate; falling back to ChunkType.CODE_BLOCK",
                raw_type,
            )
            return ChunkType.CODE_BLOCK


def run_chunking_pipeline(repository_id: str, force: bool = False) -> None:
    """
    Entry point — opens its own DB session (same reasoning as
    run_analysis_pipeline: this runs after the triggering HTTP response,
    or is chained from within another background task).

    `force=True` re-chunks every file regardless of whether its content
    hash has changed — used by the manual regenerate endpoint; normal
    automatic runs after upload always use force=False.
    """
    db = SessionLocal()
    job = IndexingJob(repository_id=repository_id, stage=JobStage.CHUNKING, status=JobStatus.RUNNING)
    db.add(job)
    db.commit()

    try:
        repo = db.get(Repository, repository_id)
        if repo is None:
            logger.error("run_chunking_pipeline: repository %s not found", repository_id)
            return

        repo.status = RepoStatus.CHUNKING
        db.commit()

        settings = get_settings()
        repo_dir = settings.repo_storage_dir / repository_id

        scan_result = scan_repository(repo_dir)
        analyzable_paths = scan_result.analyzable_file_paths
        total = len(analyzable_paths) or 1

        existing_chunked_files = {
            cf.file_path: cf
            for cf in db.query(ChunkedFile).filter(ChunkedFile.repository_id == repository_id)
        }
        seen_paths: set[str] = set()
        files_skipped_unchanged = 0
        files_chunked = 0

        for i, rel_path in enumerate(analyzable_paths):
            seen_paths.add(rel_path)
            file_disk_path = repo_dir / rel_path
            try:
                raw_bytes = file_disk_path.read_bytes()
            except OSError as exc:
                logger.warning("Could not read %s for chunking: %s", rel_path, exc)
                continue

            content_hash = hash_bytes(raw_bytes)
            prior = existing_chunked_files.get(rel_path)

            if not force and prior is not None and prior.file_content_hash == content_hash:
                files_skipped_unchanged += 1
                job.progress_percent = int((i + 1) / total * 80)
                continue

            # File is new or changed — remove its old chunks (if any) and
            # regenerate. Duplicate-reference FKs are cleaned up in the
            # dedup pass below, not here, so this delete can never violate
            # a foreign key regardless of SQLite's FK-enforcement setting.
            db.query(Chunk).filter(
                Chunk.repository_id == repository_id, Chunk.file_path == rel_path,
            ).delete(synchronize_session=False)

            parsed = parse_file(rel_path, raw_bytes)
            if parsed.error:
                # Consistent with Phase 2: an unparseable file is skipped,
                # not fatal to the whole run. It gets no chunks and no
                # ChunkedFile record, so a future run will keep retrying it.
                continue

            try:
                text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                continue

            candidates = generate_chunks_for_file(
                text, parsed.symbols, parsed.used_fallback,
                max_tokens=settings.chunk_max_tokens,
                overlap_ratio=settings.chunk_overlap_ratio,
            )

            for cand in candidates:
                db.add(Chunk(
                    repository_id=repository_id,
                    file_path=rel_path,
                    language=parsed.language,
                    chunk_type=_safe_chunk_type(cand.chunk_type),
                    symbol_name=cand.symbol_name,
                    parent_symbol_name=cand.parent_symbol_name,
                    start_line=cand.start_line,
                    end_line=cand.end_line,
                    content=cand.content,
                    token_count=cand.token_count,
                    content_hash=hash_content(cand.content),
                ))

            if prior is not None:
                prior.file_content_hash = content_hash
                prior.chunk_count = len(candidates)
                prior.chunked_at = datetime.now(timezone.utc)
            else:
                db.add(ChunkedFile(
                    repository_id=repository_id, file_path=rel_path,
                    file_content_hash=content_hash, chunk_count=len(candidates),
                ))

            files_chunked += 1
            job.progress_percent = int((i + 1) / total * 80)
            if (i + 1) % 25 == 0:
                db.commit()

        db.commit()

        # Files that existed in a previous chunking run but are no longer
        # present (deleted from the repo) — remove their stale chunks and
        # ChunkedFile record so the index doesn't reference dead files.
        stale_paths = set(existing_chunked_files) - seen_paths
        for stale_path in stale_paths:
            db.query(Chunk).filter(
                Chunk.repository_id == repository_id, Chunk.file_path == stale_path,
            ).delete(synchronize_session=False)
            db.query(ChunkedFile).filter(
                ChunkedFile.repository_id == repository_id, ChunkedFile.file_path == stale_path,
            ).delete(synchronize_session=False)
        db.commit()

        # --- Repo-wide duplicate detection (last 20%) ---
        job.progress_percent = 85
        db.commit()
        duplicate_count = _recompute_duplicates(db, repository_id)

        total_chunks = db.query(Chunk).filter(Chunk.repository_id == repository_id).count()
        chunked_file_total = db.query(ChunkedFile).filter(
            ChunkedFile.repository_id == repository_id
        ).count()

        repo.chunk_count = total_chunks
        repo.duplicate_chunk_count = duplicate_count
        repo.chunked_file_count = chunked_file_total
        repo.status = RepoStatus.CHUNKED

        job.status = JobStatus.COMPLETED
        job.progress_percent = 100
        job.message = (
            f"Chunked {files_chunked} files ({files_skipped_unchanged} unchanged, skipped), "
            f"{total_chunks} total chunks, {duplicate_count} duplicates, "
            f"{len(stale_paths)} stale files removed."
        )
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Chunking pipeline completed for repo %s: %s", repository_id, job.message)

        # Phase 4: embedding runs immediately after chunking, chained in
        # the same background task — same reasoning as the Phase 2 -> 3
        # chain (one task = one full pipeline run per upload).
        from app.services.embedding_pipeline import run_embedding_pipeline
        run_embedding_pipeline(repository_id, force=force)
        return

    except Exception as exc:  # noqa: BLE001 - top-level pipeline guard
        logger.exception("Chunking pipeline failed for repo %s", repository_id)
        db.rollback()
        job.status = JobStatus.FAILED
        job.message = str(exc)
        repo = db.get(Repository, repository_id)
        if repo is not None:
            repo.status = RepoStatus.FAILED
            repo.error_message = f"Chunking pipeline failed: {exc}"
        db.commit()
    finally:
        db.close()


def _recompute_duplicates(db: Session, repository_id: str) -> int:
    """
    Full repo-wide dedup pass: group all current chunks by content_hash,
    first-created in each group is canonical (is_duplicate=False), the
    rest point at it via duplicate_of_chunk_id. Recomputed from scratch
    every run rather than maintained incrementally — self-healing, and
    the query cost (one indexed group-by over this repo's own chunks) is
    small relative to the parsing/chunking work already done.
    """
    chunks = (
        db.query(Chunk)
        .filter(Chunk.repository_id == repository_id)
        .order_by(Chunk.created_at.asc(), Chunk.id.asc())
        .all()
    )
    by_hash: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_hash.setdefault(c.content_hash, []).append(c)

    duplicate_count = 0
    for group in by_hash.values():
        canonical, *dupes = group
        if canonical.is_duplicate or canonical.duplicate_of_chunk_id is not None:
            canonical.is_duplicate = False
            canonical.duplicate_of_chunk_id = None
        for dupe in dupes:
            dupe.is_duplicate = True
            dupe.duplicate_of_chunk_id = canonical.id
            duplicate_count += 1

    db.commit()
    return duplicate_count
