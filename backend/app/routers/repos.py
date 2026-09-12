from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File
from app.core.auth import get_current_user
from app.db.models import User
from sqlalchemy.orm import Session

from app.core.exceptions import NotImplementedFeatureError
from app.db.session import get_db
from app.schemas.repository import RepositoryListResponse, RepositoryOverview
from app.services.analysis_pipeline import run_analysis_pipeline
from app.services.ingestion import repo_service

router = APIRouter(prefix="/api/v1/repos", tags=["repositories"])


@router.post("/upload", response_model=RepositoryOverview, status_code=201)
def upload_repository(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = repo_service.ingest_zip_upload(db, file)
    repo.owner_user_id = user.id
    db.commit()
    # Phase 2 analysis (parsing, dependency graph, framework detection)
    # runs AFTER this response is sent — the upload response itself still
    # reflects the Phase 1 "scanned" state, matching the original
    # contract. Poll GET /api/v1/repos/{id} or the jobs endpoint below to
    # see it progress to "analyzed".
    background_tasks.add_task(run_analysis_pipeline, repo.id)
    return repo


@router.post("/github", response_model=RepositoryOverview)
def import_github_repository(url: str):
    # Intentionally honest: GitHub ingestion is a later phase, not built yet.
    raise NotImplementedFeatureError(
        "GitHub repository import is not implemented yet. Use ZIP upload."
    )


@router.get("", response_model=RepositoryListResponse)
def list_repositories(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repos, total = repo_service.list_repositories(db, limit=limit, offset=offset, owner_user_id=user.id)
    return RepositoryListResponse(repositories=repos, total=total)


@router.get("/{repo_id}", response_model=RepositoryOverview)
def get_repository(repo_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repo = repo_service.get_repository(db, repo_id)
    if repo.owner_user_id != user.id:
        from fastapi import HTTPException
        raise HTTPException(404, "Repository not found.")
    return repo


@router.get("/{repo_id}/events")
async def stream_repository_events(
    repo_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from fastapi.responses import StreamingResponse
    import asyncio
    import json
    from app.db.session import SessionLocal
    from app.db.models import IndexingJob, Repository

    repo = repo_service.get_repository(db, repo_id)
    if repo.owner_user_id != user.id:
        from fastapi import HTTPException
        raise HTTPException(404, "Repository not found.")

    async def event_generator():
        max_ticks = 300
        last_state = None

        for _ in range(max_ticks):
            s_db = SessionLocal()
            try:
                r = s_db.get(Repository, repo_id)
                if not r:
                    break

                job = (
                    s_db.query(IndexingJob)
                    .filter(IndexingJob.repository_id == repo_id)
                    .order_by(IndexingJob.created_at.desc())
                    .first()
                )

                status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
                stage_val = job.stage.value if (job and hasattr(job.stage, "value")) else (str(job.stage) if job else None)
                job_status_val = job.status.value if (job and hasattr(job.status, "value")) else (str(job.status) if job else None)
                progress_val = job.progress_percent if job else (100 if status_val in ("ready", "indexed") else 0)

                payload = {
                    "repository_id": r.id,
                    "name": r.name,
                    "status": status_val,
                    "stage": stage_val,
                    "job_status": job_status_val,
                    "progress_percent": progress_val,
                    "file_count": r.file_count,
                    "symbol_count": r.symbol_count,
                    "chunk_count": r.chunk_count,
                    "vector_count": r.vector_count,
                    "message": job.message if job else None,
                    "error_message": r.error_message,
                }

                state_signature = (status_val, stage_val, job_status_val, progress_val, r.vector_count, r.chunk_count, r.symbol_count)
                if state_signature != last_state:
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_state = state_signature

                if status_val in ("ready", "indexed", "failed"):
                    break
            finally:
                s_db.close()

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{repo_id}", status_code=204)
def delete_repository(repo_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repo = repo_service.get_repository(db, repo_id)
    if repo.owner_user_id != user.id:
        from fastapi import HTTPException
        raise HTTPException(404, "Repository not found.")
    repo_service.delete_repository(db, repo_id)
