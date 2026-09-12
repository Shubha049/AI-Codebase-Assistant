"""
Single entrypoint for parsing one file: `parse_file(path, source)`.
Dispatches to a real tree-sitter extractor for languages that have one,
falls back to the regex-based extractor otherwise, and — critically —
never lets one malformed/unusual file abort processing of the rest of the
repository. A parse failure becomes a `FileParseResult.error`, not an
exception that propagates up.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.services.parsing.js_ts_extractor import extract_js_ts
from app.services.parsing.language_registry import (
    EXTENSION_TO_LANGUAGE_LABEL,
    EXTENSION_TO_TS_LANGUAGE,
    has_full_ast_support,
)
from app.services.parsing.models import FileParseResult
from app.services.parsing.python_extractor import extract_python
from app.services.parsing.regex_fallback_extractor import extract_basic

logger = logging.getLogger(__name__)

_TS_DISPATCH = {
    "python": extract_python,
    "javascript": extract_js_ts,
    "typescript": extract_js_ts,
    "tsx": extract_js_ts,
}

_EXTENSION_TO_FALLBACK_KEY = {
    ".java": "java", ".go": "go", ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".rs": "rust", ".swift": "swift",
    ".kt": "kotlin", ".scala": "scala",
}

_ts_parser_cache: dict[str, object] = {}


def _get_ts_parser(language: str):
    """Module-level cache — avoids reloading a tree-sitter grammar on
    every single file (grammar load is the expensive part, not parsing)."""
    if language not in _ts_parser_cache:
        from tree_sitter_language_pack import get_parser
        _ts_parser_cache[language] = get_parser(language)
    return _ts_parser_cache[language]


def parse_file(relative_path: str, source: bytes) -> FileParseResult:
    ext = Path(relative_path).suffix.lower()
    language_label = EXTENSION_TO_LANGUAGE_LABEL.get(ext, "Other")

    if ext not in EXTENSION_TO_TS_LANGUAGE and ext not in _EXTENSION_TO_FALLBACK_KEY:
        return FileParseResult(
            file_path=relative_path, language=language_label,
            error="No extractor (tree-sitter or fallback) registered for this extension.",
        )

    try:
        if has_full_ast_support(ext):
            ts_lang = EXTENSION_TO_TS_LANGUAGE[ext]
            parser = _get_ts_parser(ts_lang)
            try:
                source.decode("utf-8")
            except UnicodeDecodeError as exc:
                return FileParseResult(file_path=relative_path, language=language_label, error=f"Not valid UTF-8: {exc}")
            tree = parser.parse(source)
            extractor = _TS_DISPATCH[ts_lang]
            symbols, imports = extractor(tree.root_node)
            return FileParseResult(
                file_path=relative_path, language=language_label,
                symbols=symbols, imports=imports,
            )
        else:
            fallback_key = _EXTENSION_TO_FALLBACK_KEY.get(ext)
            try:
                text = source.decode("utf-8")
            except UnicodeDecodeError as exc:
                return FileParseResult(file_path=relative_path, language=language_label, error=f"Not valid UTF-8: {exc}")
            symbols, imports = extract_basic(fallback_key, text)
            return FileParseResult(
                file_path=relative_path, language=language_label,
                symbols=symbols, imports=imports,
                used_fallback=True,
            )
    except Exception as exc:  # noqa: BLE001 - deliberately broad: one bad
        # file must never abort the whole repository's analysis.
        logger.warning("Failed to parse %s: %s", relative_path, exc)
        return FileParseResult(file_path=relative_path, language=language_label, error=str(exc))
