from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import CodeSymbol, DependencyEdge, IndexingJob
from app.db.session import get_db
from app.schemas.analysis import (
    AnalysisSummaryResponse,
    CodeSymbolListResponse,
    DependencyGraphResponse,
)
from app.services.ingestion.repo_service import get_repository

router = APIRouter(prefix="/api/v1/repos/{repo_id}/analysis", tags=["analysis"])


@router.get("/summary", response_model=AnalysisSummaryResponse)
def get_analysis_summary(repo_id: str, db: Session = Depends(get_db)):
    repo = get_repository(db, repo_id)  # raises 404 if missing
    latest_job = (
        db.query(IndexingJob)
        .filter(IndexingJob.repository_id == repo_id)
        .order_by(IndexingJob.created_at.desc())
        .first()
    )
    return AnalysisSummaryResponse(
        repository_id=repo.id,
        status=repo.status,
        language_breakdown=repo.language_breakdown,
        frameworks=repo.frameworks,
        build_systems=repo.build_systems,
        symbol_count=repo.symbol_count,
        parsed_file_count=repo.parsed_file_count,
        total_analyzable_files=repo.file_count,
        dependency_edge_count=repo.dependency_edge_count,
        latest_job=latest_job,
    )


@router.get("/symbols", response_model=CodeSymbolListResponse)
def list_symbols(
    repo_id: str,
    file_path: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    get_repository(db, repo_id)  # 404 check
    query = db.query(CodeSymbol).filter(CodeSymbol.repository_id == repo_id)
    if file_path:
        query = query.filter(CodeSymbol.file_path == file_path)
    total = query.count()
    symbols = query.order_by(CodeSymbol.file_path, CodeSymbol.start_line).offset(offset).limit(limit).all()
    return CodeSymbolListResponse(symbols=symbols, total=total)


@router.get("/dependency-graph", response_model=DependencyGraphResponse)
def get_dependency_graph(repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)  # 404 check
    edges = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo_id).all()
    nodes = sorted({e.source_file for e in edges} | {e.target_file for e in edges})
    return DependencyGraphResponse(nodes=nodes, edges=edges)
