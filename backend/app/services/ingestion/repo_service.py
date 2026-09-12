from __future__ import annotations

import logging
import shutil
import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.db.models import Repository, RepoStatus, SourceType
from app.services.ingestion.extraction import extract_repository, save_upload_to_tmp
from app.services.ingestion.scanner import scan_repository

logger = logging.getLogger(__name__)


def ingest_zip_upload(db: Session, upload: UploadFile) -> Repository:
    """
    Runs synchronously for Phase 1 (extraction + scanning are fast). Later
    phases (parsing/embedding) will be dispatched as background jobs off of
    the repository this creates, rather than changing this function's
    contract — routers don't need to change when that lands.
    """
    settings = get_settings()
    repo_id = str(uuid.uuid4())
    name = upload.filename.rsplit(".", 1)[0] if upload.filename else repo_id

    repo = Repository(
        id=repo_id,
        name=name,
        source_type=SourceType.ZIP,
        original_filename=upload.filename,
        storage_path=str(settings.repo_storage_dir / repo_id),
        status=RepoStatus.UPLOADING,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    try:
        repo.status = RepoStatus.EXTRACTING
        db.commit()
        tmp_zip = save_upload_to_tmp(upload, settings.max_upload_size_mb)
        extracted_dir = extract_repository(tmp_zip, repo_id)

        repo.status = RepoStatus.SCANNING
        db.commit()
        scan_result = scan_repository(extracted_dir)

        repo.file_count = scan_result.file_count
        repo.total_size_bytes = scan_result.total_size_bytes
        repo.skipped_file_count = scan_result.skipped_file_count
        repo.language_breakdown = scan_result.language_breakdown
        repo.status = RepoStatus.SCANNED
        db.commit()
        db.refresh(repo)
        logger.info(
            "Repository %s ingested: %d analyzable files, %d skipped.",
            repo_id, repo.file_count, repo.skipped_file_count,
        )
        return repo

    except Exception as exc:
        repo.status = RepoStatus.FAILED
        repo.error_message = str(exc)
        db.commit()
        # Clean up any partial extraction on disk.
        shutil.rmtree(settings.repo_storage_dir / repo_id, ignore_errors=True)
        raise


def get_repository(db: Session, repo_id: str) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise RepositoryNotFoundError(f"Repository '{repo_id}' not found.")
    return repo


def list_repositories(db: Session, limit: int = 50, offset: int = 0, owner_user_id: str | None = None) -> tuple[list[Repository], int]:
    query = db.query(Repository)
    if owner_user_id is not None:
        query = query.filter(Repository.owner_user_id == owner_user_id)
    total = query.count()
    repos = (
        query
        .order_by(Repository.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return repos, total


def delete_repository(db: Session, repo_id: str) -> None:
    settings = get_settings()
    repo = get_repository(db, repo_id)
    shutil.rmtree(settings.repo_storage_dir / repo_id, ignore_errors=True)
    db.delete(repo)
    db.commit()
