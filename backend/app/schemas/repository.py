from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import RepoStatus, SourceType


class RepositoryOverview(BaseModel):
    """Response shape for a single repository — returned on upload and on GET."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_type: SourceType
    original_filename: str | None
    status: RepoStatus
    error_message: str | None

    file_count: int
    total_size_bytes: int
    language_breakdown: dict[str, int]
    skipped_file_count: int

    # --- Phase 2: analysis results (empty/zero until analysis completes) ---
    frameworks: list[str]
    build_systems: list[str]
    symbol_count: int
    parsed_file_count: int
    dependency_edge_count: int

    # --- Phase 3: chunking results (zero until chunking completes) ---
    chunk_count: int
    duplicate_chunk_count: int
    chunked_file_count: int

    # --- Phase 4: embedding/vector results (empty/zero until indexing completes) ---
    vector_count: int
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimension: int | None
    indexed_at: datetime | None

    created_at: datetime
    updated_at: datetime


class RepositoryListResponse(BaseModel):
    repositories: list[RepositoryOverview]
    total: int
