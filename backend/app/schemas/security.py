from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class SecurityFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    category: str
    severity: str
    title: str
    description: str
    file_path: str
    line_number: int
    evidence: str
    remediation: str
    confidence: str
    created_at: datetime


class SecurityScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    status: str
    findings_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    scanned_files: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class SecuritySummaryResponse(BaseModel):
    repository_id: str
    latest_scan: SecurityScanResponse | None
    findings: list[SecurityFindingResponse]
    total_findings: int
    counts: dict[str, int]
    scanner_scope: str
