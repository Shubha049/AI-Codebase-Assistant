from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.db.models import SecurityScan
from app.db.session import SessionLocal, get_db
from app.schemas.security import SecurityFindingResponse, SecurityScanResponse, SecuritySummaryResponse
from app.services.ingestion.repo_service import get_repository
from app.services.security_service import get_findings, get_latest_scan, run_security_scan

router = APIRouter(prefix="/api/v1/repos/{repo_id}/security", tags=["security"])


def _run_background(repo_id: str, scan_id: str) -> None:
    db = SessionLocal()
    try:
        repo = get_repository(db, repo_id)
        pending = db.get(SecurityScan, scan_id)
        if pending is None:
            return
        pending.status = "running"
        db.commit()
        result = run_security_scan(db, repo)
        # run_security_scan creates the durable completed result. Remove the
        # temporary pending row so latest-scan semantics remain unambiguous.
        db.delete(pending)
        db.commit()
    except Exception as exc:
        db.rollback()
        pending = db.get(SecurityScan, scan_id)
        if pending is not None:
            pending.status = "failed"
            pending.error_message = str(exc)[:2000]
            db.commit()
    finally:
        db.close()


@router.post("/scan", response_model=SecurityScanResponse, status_code=202)
def start_security_scan(repo_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    repo = get_repository(db, repo_id)
    # Return a lightweight pending record so callers can poll.
    scan = SecurityScan(repository_id=repo.id, status="pending")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    background_tasks.add_task(_run_background, repo.id, scan.id)
    return scan


@router.get("/scans/latest", response_model=SecurityScanResponse | None)
def latest_scan(repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    return get_latest_scan(db, repo_id)


@router.get("/findings", response_model=list[SecurityFindingResponse])
def security_findings(
    repo_id: str,
    severity: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    get_repository(db, repo_id)
    return get_findings(db, repo_id, severity=severity, category=category, limit=limit)


@router.get("/summary", response_model=SecuritySummaryResponse)
def security_summary(repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    latest = get_latest_scan(db, repo_id)
    findings = get_findings(db, repo_id, limit=1000)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    return {
        "repository_id": repo_id,
        "latest_scan": latest,
        "findings": findings,
        "total_findings": len(findings),
        "counts": counts,
        "scanner_scope": "Static heuristic analysis of repository source/config files. No CVE database or exploit verification is performed.",
    }
