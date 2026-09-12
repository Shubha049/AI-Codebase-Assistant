from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import ChunkType, JobStatus


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_path: str
    language: str
    chunk_type: ChunkType
    symbol_name: str | None
    parent_symbol_name: str | None
    start_line: int
    end_line: int
    content: str
    token_count: int
    content_hash: str
    is_duplicate: bool
    duplicate_of_chunk_id: str | None
    created_at: datetime


class ChunkListResponse(BaseModel):
    chunks: list[ChunkOut]
    total: int


class ChunkingSummaryResponse(BaseModel):
    repository_id: str
    status: str
    chunk_count: int
    duplicate_chunk_count: int
    chunked_file_count: int
    chunk_type_breakdown: dict[str, int]
    job_status: JobStatus | None
    job_progress_percent: int | None
    job_message: str | None
