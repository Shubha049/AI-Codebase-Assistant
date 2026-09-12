from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Repository, SecurityFinding, SecurityScan
from app.services.ingestion.scanner import scan_repository
from app.services.security_scanner import scan_repository_files

logger = logging.getLogger(__name__)


def run_security_scan(db: Session, repo: Repository) -> SecurityScan:
    root = Path(repo.storage_path)
    # storage_path is the extracted repository root by design. Re-scan paths
    # instead of trusting a client-supplied list of files.
    scan = scan_repository(root)
    result, scanned_files = scan_repository_files(root, scan.analyzable_file_paths)

    now = datetime.now(timezone.utc)
    security_scan = SecurityScan(repository_id=repo.id, status="completed", scanned_files=scanned_files, completed_at=now)
    db.add(security_scan)
    db.flush()

    for item in result:
        db.add(SecurityFinding(
            scan_id=security_scan.id,
            repository_id=repo.id,
            rule_id=item.rule_id,
            category=item.category,
            severity=item.severity,
            title=item.title,
            description=item.description,
            file_path=item.file_path,
            line_number=item.line_number,
            evidence=item.evidence,
            remediation=item.remediation,
            confidence=item.confidence,
        ))

    counts = Counter(item.severity.value for item in result)
    security_scan.findings_count = len(result)
    security_scan.critical_count = counts["critical"]
    security_scan.high_count = counts["high"]
    security_scan.medium_count = counts["medium"]
    security_scan.low_count = counts["low"]
    security_scan.info_count = counts["info"]
    db.commit()
    db.refresh(security_scan)
    return security_scan


def get_findings(db: Session, repo_id: str, severity: str | None = None, category: str | None = None, limit: int = 200) -> list[SecurityFinding]:
    q = db.query(SecurityFinding).filter(SecurityFinding.repository_id == repo_id)
    if severity:
        q = q.filter(SecurityFinding.severity == severity)
    if category:
        q = q.filter(SecurityFinding.category == category)
    return q.order_by(SecurityFinding.severity, SecurityFinding.file_path, SecurityFinding.line_number).limit(limit).all()


def get_latest_scan(db: Session, repo_id: str) -> SecurityScan | None:
    return db.query(SecurityScan).filter(SecurityScan.repository_id == repo_id).order_by(SecurityScan.created_at.desc()).first()
