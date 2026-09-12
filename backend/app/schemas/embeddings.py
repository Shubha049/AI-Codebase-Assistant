from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import JobStatus


class EmbeddingStatusResponse(BaseModel):
    repository_id: str
    status: str
    vector_count: int
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimension: int | None
    indexed_at: datetime | None
    job_status: JobStatus | None
    job_progress_percent: int | None
    job_message: str | None


class CollectionInfoResponse(BaseModel):
    exists: bool
    collection_name: str
    points_count: int | None = None
    vector_size: int | None = None
    status: str | None = None


class ReindexRequest(BaseModel):
    force: bool = False


class ReindexResponse(BaseModel):
    detail: str
    force: bool


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class SearchResultItem(BaseModel):
    chunk_id: str
    score: float
    file_path: str
    language: str
    chunk_type: str
    symbol_name: str | None
    parent_symbol_name: str | None
    start_line: int
    end_line: int
    content: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
