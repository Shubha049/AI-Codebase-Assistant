"""
Generic sliding-window chunker over a list of lines. Used in two places:
  1. A symbol (function/method) whose own content exceeds the token
     budget — split just that symbol's lines.
  2. An entire file that only got regex-fallback parsing (Phase 2) — its
     symbol line-ranges aren't reliable (the fallback extractor mostly
     only knows a declaration's start line, not where it ends), so
     content-aware chunking isn't possible; a plain sliding window over
     the whole file is the honest fallback.

Overlap is deliberately NOT applied to normal, correctly-sized symbol
chunks elsewhere in the pipeline — two distinct functions don't benefit
from bleeding into each other. It's applied here specifically because
splitting a single oversized unit (or an un-parsed file) into artificial
boundaries can cut a thought/statement in half; a little overlap gives a
future retrieval step next-door context it would otherwise lose exactly
at each cut.
"""
from __future__ import annotations

from app.services.chunking.models import ChunkCandidate
from app.services.chunking.token_estimator import estimate_tokens


def split_lines_into_windows(
    lines: list[str],
    start_line_offset: int,
    max_tokens: int,
    overlap_ratio: float,
    chunk_type: str,
    symbol_name: str | None = None,
    parent_symbol_name: str | None = None,
) -> list[ChunkCandidate]:
    """
    `lines` are 0-indexed; `start_line_offset` is the 1-indexed file line
    number of lines[0], so callers can window an arbitrary slice of a
    file (not just the whole thing) and get correct absolute line numbers
    back.
    """
    if not lines:
        return []

    chunks: list[ChunkCandidate] = []
    i = 0
    n = len(lines)

    while i < n:
        window_lines: list[str] = []
        j = i
        while j < n:
            candidate_text = "\n".join(window_lines + [lines[j]])
            if window_lines and estimate_tokens(candidate_text) > max_tokens:
                break
            window_lines.append(lines[j])
            j += 1
        # If a single line alone exceeds max_tokens, window_lines is still
        # that one line (the inner loop's first iteration always appends
        # at least one line before the token check can reject further
        # growth) — an intentionally-accepted over-budget chunk rather
        # than silently dropping the line. See module known-limitations note.

        content = "\n".join(window_lines)
        chunks.append(ChunkCandidate(
            chunk_type=chunk_type,
            content=content,
            start_line=start_line_offset + i,
            end_line=start_line_offset + j - 1,
            token_count=estimate_tokens(content),
            symbol_name=symbol_name,
            parent_symbol_name=parent_symbol_name,
        ))

        if j >= n:
            break

        window_line_count = j - i
        # No artificial minimum-1-line floor here: for small windows (2-3
        # lines), forcing at least 1 line of overlap produces 33-50%
        # effective overlap instead of the requested ~15% — found via a
        # real test that produced 15 near-duplicate windows for 20 lines
        # of short text. Zero overlap on a small window is fine; it just
        # means that window's boundary is a clean cut.
        overlap_lines = int(window_line_count * overlap_ratio)
        next_i = j - overlap_lines
        # Still guarantee forward progress in all cases.
        i = next_i if next_i > i else i + 1

    return chunks
