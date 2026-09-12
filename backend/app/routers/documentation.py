from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import DocumentationArtifact
from app.db.session import SessionLocal, get_db
from app.schemas.documentation import DocumentationGenerateRequest, DocumentationResponse
from app.services.documentation_generator import generate_documentation, latest_documentation
from app.services.ingestion.repo_service import get_repository

router = APIRouter(prefix="/api/v1/repos/{repo_id}/documentation", tags=["documentation"])


def _run(repo_id: str, artifact_id: str, use_llm: bool) -> None:
    db = SessionLocal()
    try:
        repo = get_repository(db, repo_id)
        pending = db.get(DocumentationArtifact, artifact_id)
        if pending is None:
            return
        generate_documentation(db, repo, use_llm=use_llm)
        db.delete(pending)
        db.commit()
    except Exception as exc:
        db.rollback()
        pending = db.get(DocumentationArtifact, artifact_id)
        if pending:
            pending.status = "failed"
            pending.error_message = str(exc)[:2000]
            db.commit()
    finally:
        db.close()


@router.post("/generate", response_model=DocumentationResponse, status_code=202)
def start_documentation(
    repo_id: str,
    body: DocumentationGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    repo = get_repository(db, repo_id)
    pending = DocumentationArtifact(repository_id=repo.id, status="pending", format="markdown")
    db.add(pending)
    db.commit()
    db.refresh(pending)
    background_tasks.add_task(_run, repo.id, pending.id, body.use_llm)
    return pending


@router.get("/latest", response_model=DocumentationResponse | None)
def get_latest_documentation(repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    return latest_documentation(db, repo_id)


@router.get("/{artifact_id}", response_model=DocumentationResponse)
def get_documentation(repo_id: str, artifact_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    artifact = db.get(DocumentationArtifact, artifact_id)
    if artifact is None or artifact.repository_id != repo_id:
        raise HTTPException(404, "Documentation artifact not found.")
    return artifact
