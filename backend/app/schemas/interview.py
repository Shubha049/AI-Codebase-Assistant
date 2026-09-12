from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class InterviewGenerateRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)
    difficulty: str | None = Field(default=None, pattern="^(easy|medium|hard)$")
    question_types: list[str] | None = None
    use_llm: bool = False

class InterviewQuestion(BaseModel):
    id: str
    question_type: str
    difficulty: str
    question: str
    expected_answer: str
    explanation: str
    sources: list[dict]

class InterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    status: str
    count: int
    difficulty: str | None
    used_llm: bool
    llm_provider: str | None
    llm_model: str | None
    questions: list[InterviewQuestion]
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
