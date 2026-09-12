from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DocumentationGenerateRequest(BaseModel):
    use_llm: bool = Field(default=False, description="Optionally refine the structural document with the configured LLM provider.")


class DocumentationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    status: str
    format: str
    content: str | None
    used_llm: bool
    llm_provider: str | None
    llm_model: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
