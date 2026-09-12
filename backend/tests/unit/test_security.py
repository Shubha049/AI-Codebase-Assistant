import io
import zipfile

import pytest

from app.core.exceptions import UnsafeArchiveError, UploadTooLargeError
from app.core.security import safe_extract_zip


def _zip_with_entries(entries: dict[str, bytes], tmp_path) -> "Path":
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return zip_path


def test_safe_extract_normal_archive(tmp_path):
    zip_path = _zip_with_entries({"a.py": b"x = 1", "sub/b.py": b"y = 2"}, tmp_path)
    dest = tmp_path / "out"
    count = safe_extract_zip(zip_path, dest, max_uncompressed_size_mb=10)
    assert count == 2
    assert (dest / "a.py").read_bytes() == b"x = 1"
    assert (dest / "sub" / "b.py").read_bytes() == b"y = 2"


def test_safe_extract_rejects_relative_traversal(tmp_path):
    zip_path = _zip_with_entries({"../../evil.py": b"pwned"}, tmp_path)
    dest = tmp_path / "out"
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, dest, max_uncompressed_size_mb=10)
    # Nothing should have leaked outside `out`.
    assert not (tmp_path / "evil.py").exists()


def test_safe_extract_rejects_absolute_path(tmp_path):
    zip_path = _zip_with_entries({"/etc/evil.py": b"pwned"}, tmp_path)
    dest = tmp_path / "out"
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, dest, max_uncompressed_size_mb=10)


def test_safe_extract_rejects_oversized_archive(tmp_path):
    zip_path = _zip_with_entries({"big.py": b"x" * 1000}, tmp_path)
    dest = tmp_path / "out"
    with pytest.raises(UploadTooLargeError):
        safe_extract_zip(zip_path, dest, max_uncompressed_size_mb=0)  # 0 MB limit


def test_safe_extract_partial_failure_leaves_no_files(tmp_path):
    """If ANY entry is unsafe, nothing from the archive should be written —
    not even the safe entries that came before it in the zip."""
    zip_path = _zip_with_entries(
        {"safe.py": b"fine", "../escape.py": b"pwned"}, tmp_path
    )
    dest = tmp_path / "out"
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, dest, max_uncompressed_size_mb=10)
    assert not (dest / "safe.py").exists()
