from __future__ import annotations
from pydantic import BaseModel, Field

class QAFilters(BaseModel):
    language: str | None = None
    file_path: str | None = None
    class_name: str | None = None
    function_name: str | None = None

class AskRequest(BaseModel):
    repository_id: str
    question: str = Field(..., min_length=1, max_length=10000)
    conversation_id: str | None = None
    top_k: int = Field(default=3, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=-1, le=1)
    filters: QAFilters | None = None
    stream: bool = False

class Citation(BaseModel):
    source_id: str
    repository: str
    file: str
    chunk_id: str
    start_line: int
    end_line: int
    similarity_score: float

class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    similarity_score: float
    content: str

class QAResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[Citation]
    confidence: str
    retrieved_chunks: list[RetrievedChunkResponse]
    processing_time_ms: int
    llm_provider: str
    llm_model: str
