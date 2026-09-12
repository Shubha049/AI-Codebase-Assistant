from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import JobStage, JobStatus, RepoStatus, SymbolType


class CodeSymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_path: str
    language: str
    symbol_type: SymbolType
    name: str
    parent_name: str | None
    start_line: int
    end_line: int
    docstring: str | None


class CodeSymbolListResponse(BaseModel):
    symbols: list[CodeSymbolOut]
    total: int


class DependencyEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_file: str
    target_file: str


class DependencyGraphResponse(BaseModel):
    nodes: list[str]  # every file that appears as a source or target
    edges: list[DependencyEdgeOut]


class FrameworkOut(BaseModel):
    name: str


class AnalysisJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stage: JobStage
    status: JobStatus
    progress_percent: int
    message: str | None
    created_at: datetime
    completed_at: datetime | None


class AnalysisSummaryResponse(BaseModel):
    repository_id: str
    status: RepoStatus
    language_breakdown: dict[str, int]
    frameworks: list[str]
    build_systems: list[str]
    symbol_count: int
    parsed_file_count: int
    total_analyzable_files: int
    dependency_edge_count: int
    latest_job: AnalysisJobOut | None
