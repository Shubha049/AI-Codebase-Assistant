from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.limiter import limiter
from app.db.models import InterviewQuestionSet
from app.db.session import SessionLocal, get_db
from app.schemas.interview import InterviewGenerateRequest, InterviewResponse
from app.services.ingestion.repo_service import get_repository
from app.services.interview_generator import generate_interview, latest_interview

router = APIRouter(prefix="/api/v1/repos/{repo_id}/interview", tags=["interview"])

def _run(repo_id: str, record_id: str, body: InterviewGenerateRequest):
    db = SessionLocal()
    try:
        repo = get_repository(db, repo_id)
        generate_interview(db, repo, body.count, body.difficulty, body.question_types, body.use_llm, record_id=record_id)
    except Exception as exc:
        db.rollback(); pending = db.get(InterviewQuestionSet, record_id)
        if pending:
            pending.status = "failed"; pending.error_message = str(exc)[:2000]; db.commit()
    finally:
        db.close()

@router.post("/generate", response_model=InterviewResponse, status_code=202)
@limiter.limit("15/minute")
def start(
    request: Request,
    repo_id: str,
    body: InterviewGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    repo = get_repository(db, repo_id)
    pending = InterviewQuestionSet(repository_id=repo.id, status="pending", requested_count=body.count, difficulty=body.difficulty, questions=[])
    db.add(pending); db.commit(); db.refresh(pending)
    background_tasks.add_task(_run, repo.id, pending.id, body)
    return pending

@router.get("/latest", response_model=InterviewResponse | None)
def latest(repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    return latest_interview(db, repo_id)

@router.get("/{set_id}", response_model=InterviewResponse)
def get_set(repo_id: str, set_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    record = db.get(InterviewQuestionSet, set_id)
    if not record or record.repository_id != repo_id:
        raise HTTPException(404, "Interview question set not found.")
    return record
