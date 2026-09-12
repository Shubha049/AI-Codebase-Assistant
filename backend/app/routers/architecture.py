from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.architecture import (
    ArchitectureFileResponse,
    ArchitectureGraphResponse,
    ArchitectureImpactResponse,
    ArchitectureOverviewResponse,
)
from app.services.architecture.explorer import get_file_detail, get_graph, get_impact, get_overview
from app.services.ingestion.repo_service import get_repository

router = APIRouter(prefix="/api/v1/repos/{repo_id}/architecture", tags=["architecture"])


@router.get("/overview", response_model=ArchitectureOverviewResponse)
def architecture_overview(repo_id: str, db: Session = Depends(get_db)):
    repo = get_repository(db, repo_id)
    return get_overview(db, repo)


@router.get("/graph", response_model=ArchitectureGraphResponse)
def architecture_graph(
    repo_id: str,
    max_nodes: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    get_repository(db, repo_id)
    return get_graph(db, repo_id, max_nodes=max_nodes)


@router.get("/files/{file_path:path}", response_model=ArchitectureFileResponse)
def architecture_file(file_path: str, repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)
    result = get_file_detail(db, repo_id, file_path)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Architecture data not found for file")
    return result


@router.get("/impact", response_model=ArchitectureImpactResponse)
def architecture_impact(
    repo_id: str,
    file_path: str,
    depth: int = Query(2, ge=1, le=10),
    db: Session = Depends(get_db),
):
    get_repository(db, repo_id)
    result = get_impact(db, repo_id, file_path, depth=depth)
    if not result["dependencies"] and not result["dependents"]:
        # A genuinely isolated file is valid architecture data; only reject
        # paths that are absent from all analysis tables.
        if get_file_detail(db, repo_id, file_path) is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="File not found in repository analysis")
    return result
