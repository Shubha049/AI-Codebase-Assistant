"""
Handles the "get the uploaded ZIP safely onto disk and extracted" stage.
Delegates the actual unsafe-path defense to app.core.security.
"""
from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings
from app.core.exceptions import InvalidUploadError, UploadTooLargeError
from app.core.security import safe_extract_zip


def save_upload_to_tmp(upload: UploadFile, max_size_mb: int) -> Path:
    """Streams the upload to disk in chunks (never loads the whole file
    into memory), enforcing the size limit as it goes rather than trusting
    a Content-Length header."""
    settings = get_settings()
    if not upload.filename or not upload.filename.lower().endswith(".zip"):
        raise InvalidUploadError("Only .zip files are accepted.")

    max_bytes = max_size_mb * 1024 * 1024
    tmp_path = settings.upload_tmp_dir / f"{uuid.uuid4()}.zip"

    written = 0
    chunk_size = 1024 * 1024
    with open(tmp_path, "wb") as out:
        while True:
            chunk = upload.file.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                out.close()
                tmp_path.unlink(missing_ok=True)
                raise UploadTooLargeError(
                    f"Upload exceeds the {max_size_mb} MB limit."
                )
            out.write(chunk)

    if written == 0:
        tmp_path.unlink(missing_ok=True)
        raise InvalidUploadError("Uploaded file is empty.")

    if not zipfile.is_zipfile(tmp_path):
        tmp_path.unlink(missing_ok=True)
        raise InvalidUploadError("Uploaded file is not a valid ZIP archive.")

    return tmp_path


def extract_repository(zip_path: Path, repo_id: str) -> Path:
    """Extracts the validated zip into its own storage directory, named by
    repository id. Cleans up the temp zip afterward either way."""
    settings = get_settings()
    dest_dir = settings.repo_storage_dir / repo_id
    try:
        safe_extract_zip(zip_path, dest_dir, settings.max_upload_size_mb * 4)
        return dest_dir
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    finally:
        zip_path.unlink(missing_ok=True)
