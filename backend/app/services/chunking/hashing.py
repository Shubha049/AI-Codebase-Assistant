"""
Content hashing shared by chunk-level duplicate detection and
file-level incremental-indexing (skip unchanged files).
"""
from __future__ import annotations

import hashlib


def hash_content(text: str) -> str:
    """SHA-256 hex digest. Text is NOT normalized (no whitespace
    stripping) — two chunks are only considered duplicates if their
    content is byte-for-byte identical, which is the correct, safe
    default for detecting real copy-pasted code rather than merely
    similar-looking code."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
