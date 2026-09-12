"""Plain dataclasses representing what parsing a single file produces.
Kept separate from the DB models so the parsing layer has no ORM/session
dependency — it's pure function of (file content) -> (extracted data),
which is what makes it independently unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedSymbol:
    symbol_type: str            # "function" | "method" | "class" | "arrow_function"
    name: str
    start_line: int             # 1-indexed
    end_line: int
    parent_name: str | None = None
    docstring: str | None = None


@dataclass
class ExtractedImport:
    module: str                 # raw target as written, e.g. "app.services.foo" or "./utils"
    imported_names: list[str] = field(default_factory=list)
    line_number: int = 0        # 1-indexed


@dataclass
class FileParseResult:
    file_path: str
    language: str
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    error: str | None = None    # set instead of raising, so one bad file never aborts a whole repo
    used_fallback: bool = False  # True = regex-based basic extraction, not real AST
