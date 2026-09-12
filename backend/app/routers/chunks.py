from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Chunk, IndexingJob, JobStage
from app.db.session import get_db
from app.schemas.chunking import ChunkingSummaryResponse, ChunkListResponse
from app.services.chunk_generation_pipeline import run_chunking_pipeline
from app.services.ingestion.repo_service import get_repository

router = APIRouter(prefix="/api/v1/repos/{repo_id}/chunks", tags=["chunks"])


@router.get("", response_model=ChunkListResponse)
def list_chunks(
    repo_id: str,
    file_path: str | None = None,
    chunk_type: str | None = None,
    exclude_duplicates: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    get_repository(db, repo_id)  # 404 check
    query = db.query(Chunk).filter(Chunk.repository_id == repo_id)
    if file_path:
        query = query.filter(Chunk.file_path == file_path)
    if chunk_type:
        query = query.filter(Chunk.chunk_type == chunk_type)
    if exclude_duplicates:
        query = query.filter(Chunk.is_duplicate.is_(False))
    total = query.count()
    chunks = query.order_by(Chunk.file_path, Chunk.start_line).offset(offset).limit(limit).all()
    return ChunkListResponse(chunks=chunks, total=total)


@router.get("/summary", response_model=ChunkingSummaryResponse)
def get_chunking_summary(repo_id: str, db: Session = Depends(get_db)):
    repo = get_repository(db, repo_id)  # 404 check

    type_counts = (
        db.query(Chunk.chunk_type, func.count(Chunk.id))
        .filter(Chunk.repository_id == repo_id)
        .group_by(Chunk.chunk_type)
        .all()
    )
    breakdown = {t.value: c for t, c in type_counts}

    latest_job = (
        db.query(IndexingJob)
        .filter(IndexingJob.repository_id == repo_id, IndexingJob.stage == JobStage.CHUNKING)
        .order_by(IndexingJob.created_at.desc())
        .first()
    )

    return ChunkingSummaryResponse(
        repository_id=repo.id,
        status=repo.status.value,
        chunk_count=repo.chunk_count,
        duplicate_chunk_count=repo.duplicate_chunk_count,
        chunked_file_count=repo.chunked_file_count,
        chunk_type_breakdown=breakdown,
        job_status=latest_job.status if latest_job else None,
        job_progress_percent=latest_job.progress_percent if latest_job else None,
        job_message=latest_job.message if latest_job else None,
    )


@router.post("/regenerate", status_code=202)
def regenerate_chunks(
    repo_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Manually re-triggers chunking for an already-analyzed repository.
    `force=false` (default) exercises incremental indexing: files whose
    content hasn't changed since the last chunking pass are skipped.
    `force=true` re-chunks every file regardless.
    """
    get_repository(db, repo_id)  # 404 check
    background_tasks.add_task(run_chunking_pipeline, repo_id, force)
    return {"detail": "Chunking regeneration started.", "force": force}
