"""
Repository scanner: walks an extracted repository directory and produces
language breakdown + file/size stats. No parsing of file *contents* into
AST happens here — that's Phase 3 (tree-sitter). This stage only looks at
extensions and whether a file is readable as text, which is enough to
give the user a real, honest picture of what's in the repo immediately.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rs": "Rust",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
}


@dataclass
class ScanResult:
    file_count: int = 0
    total_size_bytes: int = 0
    skipped_file_count: int = 0
    language_breakdown: dict[str, int] = field(default_factory=dict)
    analyzable_file_paths: list[str] = field(default_factory=list)  # relative paths, for later phases


def scan_repository(root_dir: Path) -> ScanResult:
    settings = get_settings()
    skip_dirs = set(settings.skip_dir_names)
    analyzable_exts = set(settings.analyzable_extensions)

    result = ScanResult()

    for path in root_dir.rglob("*"):
        # Prune skipped directories by checking any path component.
        if any(part in skip_dirs for part in path.relative_to(root_dir).parts):
            continue

        if not path.is_file():
            continue

        try:
            size = path.stat().st_size
        except OSError:
            result.skipped_file_count += 1
            continue

        ext = path.suffix.lower()
        if ext not in analyzable_exts:
            continue

        # Confirm it's actually text (extension can lie — e.g. a binary
        # blob someone named `data.json`).
        if not _looks_like_text(path):
            result.skipped_file_count += 1
            continue

        result.file_count += 1
        result.total_size_bytes += size
        rel = path.relative_to(root_dir).as_posix()
        result.analyzable_file_paths.append(rel)

        language = EXTENSION_TO_LANGUAGE.get(ext, "Other")
        result.language_breakdown[language] = result.language_breakdown.get(language, 0) + 1

        if result.file_count >= settings.max_files_per_repo:
            logger.warning(
                "Repository exceeds max_files_per_repo (%d); stopping scan early.",
                settings.max_files_per_repo,
            )
            break

    return result


def _looks_like_text(path: Path, sniff_bytes: int = 8192) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
