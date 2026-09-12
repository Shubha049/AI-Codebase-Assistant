"""
Path-safety helpers used by the ingestion service.

The critical property `is_within_directory` / `safe_extract_zip` enforce:
a ZIP entry is only ever extracted if its *resolved, absolute* final path
is still inside the target directory. This defeats "zip-slip" archives
that use entry names like `../../etc/passwd` or absolute paths to escape
the extraction directory. Symlink entries are rejected outright rather
than followed, since a symlink could point outside the sandbox even if
its own name looks safe.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from app.core.exceptions import UnsafeArchiveError, UploadTooLargeError

# Defends against zip-bombs: cap total uncompressed size regardless of the
# declared upload size (a tiny ZIP can decompress to gigabytes).
MAX_UNCOMPRESSED_RATIO = 100  # reject if uncompressed > 100x compressed
MAX_SINGLE_FILE_UNCOMPRESSED_MB = 200


def is_within_directory(base_dir: Path, target: Path) -> bool:
    base_dir = base_dir.resolve()
    target = target.resolve()
    return base_dir == target or base_dir in target.parents


def safe_extract_zip(zip_path: Path, dest_dir: Path, max_uncompressed_size_mb: int) -> int:
    """
    Extracts `zip_path` into `dest_dir`, rejecting the whole archive if any
    entry is unsafe. Returns the number of files extracted.

    Raises UnsafeArchiveError / UploadTooLargeError instead of partially
    extracting an archive that turns out to be malicious partway through.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = max_uncompressed_size_mb * 1024 * 1024

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()

        # --- Pass 1: validate every entry before extracting anything ---
        total_uncompressed = 0
        for info in infos:
            if info.is_dir():
                continue

            # Reject absolute paths and traversal sequences outright.
            name = info.filename
            if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                raise UnsafeArchiveError(
                    f"Archive entry '{name}' uses an unsafe path and was rejected."
                )

            dest_path = dest_dir / name
            if not is_within_directory(dest_dir, dest_path):
                raise UnsafeArchiveError(
                    f"Archive entry '{name}' would extract outside the target "
                    f"directory and was rejected."
                )

            # Symlinks: Unix zip symlink entries have external_attr high bits
            # set to S_IFLNK (0xA000). Reject them — never follow.
            mode = (info.external_attr >> 16) & 0xFFFF
            is_symlink = (mode & 0xF000) == 0xA000
            if is_symlink:
                raise UnsafeArchiveError(
                    f"Archive entry '{name}' is a symlink and was rejected."
                )

            if info.file_size > MAX_SINGLE_FILE_UNCOMPRESSED_MB * 1024 * 1024:
                raise UnsafeArchiveError(
                    f"Archive entry '{name}' exceeds the per-file size limit."
                )

            total_uncompressed += info.file_size

        if total_uncompressed > max_bytes:
            raise UploadTooLargeError(
                f"Archive would extract to {total_uncompressed / 1024 / 1024:.1f} MB, "
                f"exceeding the {max_uncompressed_size_mb} MB limit."
            )

        compressed_total = sum(i.compress_size for i in infos) or 1
        if total_uncompressed / compressed_total > MAX_UNCOMPRESSED_RATIO:
            raise UnsafeArchiveError(
                "Archive's compression ratio is suspiciously high (possible zip bomb)."
            )

        # --- Pass 2: everything validated, now actually extract ---
        extracted = 0
        for info in infos:
            if info.is_dir():
                continue
            dest_path = dest_dir / info.filename
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest_path, "wb") as dst:
                dst.write(src.read())
            extracted += 1

    return extracted
