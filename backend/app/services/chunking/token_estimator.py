"""
Approximate token counting.

This is NOT a real tokenizer — no embedding/LLM provider has been chosen
yet (that's Phase 4), so there's no specific vocabulary to match. Using
the common "~4 characters per token" rule of thumb for English text and
most programming languages. This will over/under-count for
tokenizer-unfriendly content (long identifiers, dense symbols, non-Latin
text) — acceptable for sizing decisions during chunking, but callers
should not treat this as an exact count.
"""
from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / _CHARS_PER_TOKEN))
