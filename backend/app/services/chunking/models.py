from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkCandidate:
    chunk_type: str  # matches app.db.models.ChunkType values
    content: str
    start_line: int  # 1-indexed, inclusive
    end_line: int     # 1-indexed, inclusive
    token_count: int
    symbol_name: str | None = None
    parent_symbol_name: str | None = None
