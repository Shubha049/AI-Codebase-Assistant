"""
Basic, regex-based symbol/import extraction for languages that don't have
a hand-written tree-sitter extractor in this codebase (Java, Go, Ruby,
PHP, C/C++/C#, Rust, Swift, Kotlin, Scala).

This is deliberately NOT presented as equivalent to the tree-sitter path:
it catches common, conventionally-formatted declarations and will miss
multi-line signatures, unusual formatting, and language edge cases that a
real parser wouldn't. Every result from this module is tagged
`parse_status="basic_fallback"` by the caller so nothing downstream
mistakes a regex match for a verified AST node.
"""
from __future__ import annotations

import re

from app.services.parsing.models import ExtractedImport, ExtractedSymbol

_FUNCTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "java": [
        re.compile(
            r"^[ \t]*(?:public|private|protected|static|final|[ \t])*"
            r"[\w<>\[\],\s]+?\s+(?P<name>[a-zA-Z_]\w*)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
            re.MULTILINE,
        ),
    ],
    "go": [
        # Receiver methods: `func (s *Server) Start()` — capture BOTH the
        # receiver type (as parent) and the method name. Tried as first
        # pattern so plain functions (no receiver) fall through to the
        # second pattern below.
        re.compile(
            r"^func\s+\([^)]*?\*?(?P<receiver>[A-Z]\w*)\)\s+(?P<name>[a-zA-Z_]\w*)\s*\(",
            re.MULTILINE,
        ),
        re.compile(r"^func\s+(?P<name>[a-zA-Z_]\w*)\s*\(", re.MULTILINE),
    ],
    "ruby": [
        re.compile(r"^[ \t]*def\s+(?P<name>[a-zA-Z_]\w*[?!]?)", re.MULTILINE),
    ],
    "php": [
        re.compile(r"^[ \t]*(?:public|private|protected|static|[ \t])*function\s+(?P<name>[a-zA-Z_]\w*)\s*\(", re.MULTILINE),
    ],
    "c": [
        re.compile(r"^[\w\*]+\s+(?P<name>[a-zA-Z_]\w*)\s*\([^;{]*\)\s*\{", re.MULTILINE),
    ],
    "cpp": [
        re.compile(r"^[\w:<>\*&~]+\s+(?P<name>[a-zA-Z_]\w*)\s*\([^;{]*\)\s*(?:const\s*)?\{", re.MULTILINE),
    ],
    "csharp": [
        re.compile(
            r"^[ \t]*(?:public|private|protected|internal|static|async|virtual|override|[ \t])*"
            r"[\w<>\[\],\s]+?\s+(?P<name>[a-zA-Z_]\w*)\s*\([^)]*\)\s*\{",
            re.MULTILINE,
        ),
    ],
    "rust": [
        re.compile(r"^[ \t]*(?:pub\s+)?fn\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE),
    ],
    "swift": [
        re.compile(r"^[ \t]*(?:public|private|internal|[ \t])*func\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE),
    ],
    "kotlin": [
        re.compile(r"^[ \t]*(?:public|private|internal|[ \t])*fun\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE),
    ],
    "scala": [
        re.compile(r"^[ \t]*(?:private|protected|[ \t])*def\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE),
    ],
}

_CLASS_PATTERNS: dict[str, list[re.Pattern]] = {
    "java": [re.compile(r"^[ \t]*(?:public|private|protected|abstract|final|[ \t])*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "go": [re.compile(r"^type\s+(?P<name>[a-zA-Z_]\w*)\s+struct", re.MULTILINE)],
    "ruby": [re.compile(r"^[ \t]*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "php": [re.compile(r"^[ \t]*(?:abstract\s+|final\s+)?class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "cpp": [re.compile(r"^[ \t]*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "csharp": [re.compile(r"^[ \t]*(?:public|private|internal|abstract|sealed|[ \t])*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "rust": [re.compile(r"^[ \t]*(?:pub\s+)?struct\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "swift": [re.compile(r"^[ \t]*(?:public|private|internal|[ \t])*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "kotlin": [re.compile(r"^[ \t]*(?:public|private|internal|[ \t])*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
    "scala": [re.compile(r"^[ \t]*(?:private|protected|[ \t])*class\s+(?P<name>[a-zA-Z_]\w*)", re.MULTILINE)],
}

_IMPORT_PATTERNS: dict[str, re.Pattern] = {
    "java": re.compile(r"^[ \t]*import\s+(?:static\s+)?(?P<module>[\w.]+(?:\.\*)?)\s*;", re.MULTILINE),
    "go": re.compile(r'^[ \t]*(?:import\s+)?(?:[a-zA-Z_]\w*\s+)?"(?P<module>[\w./\-]+)"\s*$', re.MULTILINE),
    "ruby": re.compile(r"^[ \t]*require(?:_relative)?\s+['\"](?P<module>[\w./\-]+)['\"]", re.MULTILINE),
    "php": re.compile(r"^[ \t]*use\s+(?P<module>[\w\\]+)\s*;", re.MULTILINE),
    "c": re.compile(r'^[ \t]*#include\s+[<"](?P<module>[\w./\-]+)[>"]', re.MULTILINE),
    "cpp": re.compile(r'^[ \t]*#include\s+[<"](?P<module>[\w./\-]+)[>"]', re.MULTILINE),
    "csharp": re.compile(r"^[ \t]*using\s+(?P<module>[\w.]+)\s*;", re.MULTILINE),
    "rust": re.compile(r"^[ \t]*use\s+(?P<module>[\w:]+)", re.MULTILINE),
    "swift": re.compile(r"^[ \t]*import\s+(?P<module>[\w.]+)", re.MULTILINE),
    "kotlin": re.compile(r"^[ \t]*import\s+(?P<module>[\w.]+)", re.MULTILINE),
    "scala": re.compile(r"^[ \t]*import\s+(?P<module>[\w.]+)", re.MULTILINE),
}


def extract_basic(language: str, source: str) -> tuple[list[ExtractedSymbol], list[ExtractedImport]]:
    symbols: list[ExtractedSymbol] = []

    for pattern in _CLASS_PATTERNS.get(language, []):
        for m in pattern.finditer(source):
            line = source.count("\n", 0, m.start()) + 1
            symbols.append(ExtractedSymbol(
                symbol_type="class", name=m.group("name"),
                start_line=line, end_line=line,
            ))

    class_line_ranges = _approximate_class_ranges(source, language)

    for pattern in _FUNCTION_PATTERNS.get(language, []):
        for m in pattern.finditer(source):
            line = source.count("\n", 0, m.start()) + 1
            group_dict = m.groupdict()
            receiver = group_dict.get("receiver")  # Go receiver-method syntax
            parent = receiver if receiver else _containing_class(line, class_line_ranges)
            symbols.append(ExtractedSymbol(
                symbol_type="method" if parent else "function",
                name=m.group("name"),
                start_line=line, end_line=line,
                parent_name=parent,
            ))

    imports: list[ExtractedImport] = []
    import_pattern = _IMPORT_PATTERNS.get(language)
    if import_pattern:
        for m in import_pattern.finditer(source):
            line = source.count("\n", 0, m.start()) + 1
            imports.append(ExtractedImport(module=m.group("module"), line_number=line))

    return symbols, imports


def _approximate_class_ranges(source: str, language: str) -> list[tuple[int, int, str]]:
    """
    Very rough heuristic to guess which lines fall "inside" a class, so
    top-level vs. method functions can be told apart without a real AST.
    Deliberately approximate — documented as a known limitation.
    """
    if language == "ruby":
        return _approximate_class_ranges_end_keyword(source)
    return _approximate_class_ranges_braces(source, language)


def _approximate_class_ranges_braces(source: str, language: str) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    for pattern in _CLASS_PATTERNS.get(language, []):
        for m in pattern.finditer(source):
            start_line = source.count("\n", 0, m.start()) + 1
            brace_start = source.find("{", m.end())
            if brace_start == -1:
                continue
            depth = 1
            i = brace_start + 1
            while i < len(source) and depth > 0:
                if source[i] == "{":
                    depth += 1
                elif source[i] == "}":
                    depth -= 1
                i += 1
            end_line = source.count("\n", 0, i) + 1
            ranges.append((start_line, end_line, m.group("name")))
    return ranges


def _approximate_class_ranges_end_keyword(source: str) -> list[tuple[int, int, str]]:
    """
    Ruby closes blocks with a bare `end` line rather than a brace. Counts
    `class`/`def`/`module`/`do`/`if`/`unless` openers against `end`
    closers to find each `class ... end` span. Approximate by design —
    doesn't handle `if ... end` written on one line, heredocs, etc.
    """
    ranges: list[tuple[int, int, str]] = []
    opener_re = re.compile(r"^[ \t]*(class|def|module|do\b|if\b|unless\b)\b", re.MULTILINE)
    end_re = re.compile(r"^[ \t]*end\b", re.MULTILINE)
    for pattern in _CLASS_PATTERNS.get("ruby", []):
        for m in pattern.finditer(source):
            start_line = source.count("\n", 0, m.start()) + 1
            lines = source.split("\n")
            depth = 1
            end_line = start_line
            for idx in range(start_line, len(lines)):  # start_line is already 1 past the class line (0-indexed continuation)
                line_text = lines[idx]
                if opener_re.match(line_text):
                    depth += 1
                elif end_re.match(line_text):
                    depth -= 1
                    if depth == 0:
                        end_line = idx + 1
                        break
            ranges.append((start_line, end_line, m.group("name")))
    return ranges


def _containing_class(line: int, ranges: list[tuple[int, int, str]]) -> str | None:
    best: str | None = None
    best_span = None
    for start, end, name in ranges:
        if start <= line <= end:
            span = end - start
            if best_span is None or span < best_span:
                best, best_span = name, span
    return best
