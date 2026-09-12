"""
Turns a parsed file (Phase 2's FileParseResult) into a set of chunks that
cover the file's ENTIRE content — not just what got recognized as a
symbol. Three cases:

1. `used_fallback=True` (regex-based parsing, Phase 2): symbol line-ranges
   aren't reliable — the fallback extractor mostly only knows a
   declaration's start line, not its end. Content-aware chunking isn't
   trustworthy here, so the whole file is chunked with an honest sliding
   window (chunk_type=FILE_WINDOW) instead.

2. A file with real AST symbols (Python/JS/TS/TSX): each top-level
   function/class gets a chunk from its own start/end lines. Classes with
   methods get split into a CLASS_HEADER chunk (signature + docstring)
   plus one chunk per method. Any symbol whose own content still exceeds
   the token budget gets sliding-window split.

3. Gaps — lines not covered by any symbol (imports, top-level statements
   between/after symbols) — become MODULE_LEVEL chunks, so nothing in the
   file is silently excluded.
"""
from __future__ import annotations

import logging

from app.services.chunking.line_window_splitter import split_lines_into_windows
from app.services.chunking.models import ChunkCandidate
from app.services.chunking.token_estimator import estimate_tokens
from app.services.parsing.models import ExtractedSymbol

logger = logging.getLogger(__name__)


def map_symbol_to_chunk_type(symbol_type: str, parent_name: str | None = None) -> str:
    """
    Map any AST symbol_type or tree-sitter node kind to a valid ChunkType string.
    Ensures 'arrow_function', 'generator_function', 'function_declaration', etc.
    correctly map to 'function' (or 'method' if inside a parent class),
    and classes/interfaces/structs map to 'class'.
    Unrecognized types fall back safely to 'code_block' with a warning.
    """
    st = (symbol_type or "").lower().strip()

    # Functions / Callables
    if st in {
        "function",
        "arrow_function",
        "function_declaration",
        "function_definition",
        "async_function_definition",
        "generator_function",
        "generator_function_declaration",
        "function_expression",
        "lambda",
        "closure",
    }:
        return "method" if parent_name else "function"

    # Methods
    if st in {
        "method",
        "method_definition",
        "generator_method",
        "getter",
        "setter",
        "constructor",
        "object_method",
    }:
        return "method"

    # Classes / Types
    if st in {
        "class",
        "class_declaration",
        "class_definition",
        "abstract_class_declaration",
        "class_expression",
        "interface",
        "interface_declaration",
        "struct",
        "struct_declaration",
        "type_alias",
        "type_alias_declaration",
        "enum",
        "enum_declaration",
    }:
        return "class"

    # Recognized chunk types
    if st in {
        "class_header",
        "module_level",
        "function_window",
        "method_window",
        "file_window",
        "code_block",
        "unknown",
    }:
        return st

    logger.warning("Unmapped symbol_type %r encountered; defaulting to 'code_block'", symbol_type)
    return "code_block"


def generate_chunks_for_file(
    file_text: str,
    symbols: list[ExtractedSymbol],
    used_fallback: bool,
    max_tokens: int,
    overlap_ratio: float,
) -> list[ChunkCandidate]:
    lines = file_text.split("\n")
    total_lines = len(lines)
    if total_lines == 0 or (total_lines == 1 and not lines[0]):
        return []

    if used_fallback or not symbols:
        return split_lines_into_windows(
            lines, 1, max_tokens, overlap_ratio, chunk_type="file_window",
        )

    top_level = sorted(
        [s for s in symbols if s.parent_name is None], key=lambda s: s.start_line
    )
    children_by_parent: dict[str, list[ExtractedSymbol]] = {}
    for s in symbols:
        if s.parent_name is not None:
            children_by_parent.setdefault(s.parent_name, []).append(s)
    for v in children_by_parent.values():
        v.sort(key=lambda s: s.start_line)

    chunks: list[ChunkCandidate] = []
    covered_lines: set[int] = set()

    for sym in top_level:
        sym_lines = lines[sym.start_line - 1: sym.end_line]  # slice is 0-indexed, end exclusive
        sym_text = "\n".join(sym_lines)
        sym_tokens = estimate_tokens(sym_text)
        covered_lines.update(range(sym.start_line, sym.end_line + 1))

        methods = children_by_parent.get(sym.name, [])

        if not methods:
            # No methods to split by — either a plain function / arrow-function, or a
            # class with no methods (e.g. a dataclass/constants holder).
            c_type = map_symbol_to_chunk_type(sym.symbol_type, sym.parent_name)
            if sym_tokens <= max_tokens:
                chunks.append(ChunkCandidate(
                    chunk_type=c_type,
                    content=sym_text,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    token_count=sym_tokens,
                    symbol_name=sym.name,
                    parent_symbol_name=None,
                ))
            else:
                window_type = "function_window" if c_type != "class" else "class_header"
                chunks.extend(split_lines_into_windows(
                    sym_lines, sym.start_line, max_tokens, overlap_ratio,
                    chunk_type=window_type, symbol_name=sym.name,
                ))
            continue

        # A class WITH methods always gets split into a header chunk plus
        # one chunk per method — regardless of whether the whole class
        # would fit under the token budget as a single chunk. This is
        # deliberate, not just a size-driven fallback: per-method
        # granularity is what makes a later "explain how X works" lookup
        # land on the specific method instead of the whole class body.
        first_method_line = methods[0].start_line
        header_lines = lines[sym.start_line - 1: first_method_line - 1]
        header_text = "\n".join(header_lines)
        if header_text.strip():
            header_tokens = estimate_tokens(header_text)
            if header_tokens <= max_tokens:
                chunks.append(ChunkCandidate(
                    chunk_type="class_header",
                    content=header_text,
                    start_line=sym.start_line,
                    end_line=first_method_line - 1,
                    token_count=header_tokens,
                    symbol_name=sym.name,
                ))
            else:
                chunks.extend(split_lines_into_windows(
                    header_lines, sym.start_line, max_tokens, overlap_ratio,
                    chunk_type="class_header", symbol_name=sym.name,
                ))

        for method in methods:
            method_lines = lines[method.start_line - 1: method.end_line]
            method_text = "\n".join(method_lines)
            method_tokens = estimate_tokens(method_text)
            covered_lines.update(range(method.start_line, method.end_line + 1))
            m_type = map_symbol_to_chunk_type(method.symbol_type, sym.name)
            if m_type not in ("method", "method_window"):
                m_type = "method"
            if method_tokens <= max_tokens:
                chunks.append(ChunkCandidate(
                    chunk_type=m_type,
                    content=method_text,
                    start_line=method.start_line,
                    end_line=method.end_line,
                    token_count=method_tokens,
                    symbol_name=method.name,
                    parent_symbol_name=sym.name,
                ))
            else:
                chunks.extend(split_lines_into_windows(
                    method_lines, method.start_line, max_tokens, overlap_ratio,
                    chunk_type="method_window", symbol_name=method.name,
                    parent_symbol_name=sym.name,
                ))

    # --- Gap-filling: any lines not covered by a top-level symbol or its
    # methods (imports, module-level statements, code between/after
    # symbols) become MODULE_LEVEL chunks, so the file's full content is
    # represented somewhere in the chunk set. ---
    for start, end in _find_gaps(total_lines, covered_lines):
        gap_lines = lines[start - 1: end]
        gap_text = "\n".join(gap_lines)
        if not gap_text.strip():
            continue  # pure whitespace between symbols — nothing to chunk
        gap_tokens = estimate_tokens(gap_text)
        if gap_tokens <= max_tokens:
            chunks.append(ChunkCandidate(
                chunk_type="module_level", content=gap_text,
                start_line=start, end_line=end, token_count=gap_tokens,
            ))
        else:
            chunks.extend(split_lines_into_windows(
                gap_lines, start, max_tokens, overlap_ratio, chunk_type="module_level",
            ))

    chunks.sort(key=lambda c: c.start_line)
    return chunks


def _find_gaps(total_lines: int, covered: set[int]) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    line = 1
    while line <= total_lines:
        if line in covered:
            line += 1
            continue
        gap_start = line
        while line <= total_lines and line not in covered:
            line += 1
        gaps.append((gap_start, line - 1))
    return gaps
