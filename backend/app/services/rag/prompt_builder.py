from __future__ import annotations

from dataclasses import dataclass

from app.services.rag.retrieval import RetrievedChunk


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    user_prompt: str
    chunks: list[RetrievedChunk]


SYSTEM = """You are an AI assistant for a software repository. Answer ONLY from retrieved repository evidence. If the evidence is insufficient, say so explicitly. Never invent files, symbols, line numbers, APIs, or behavior. Cite evidence using [S1], [S2], etc. Preserve exact file paths and line ranges from the supplied context."""


def build_prompt(question: str, chunks: list[RetrievedChunk], history: list[dict[str, str]] | None = None, max_chars: int = 24000) -> PromptBundle:
    # Collapse exact logical duplicates before assigning citation IDs. If
    # duplicates have different scores, keep the strongest evidence rather
    # than whichever happened to arrive first from the vector store.
    best_by_key = {}
    for c in chunks:
        key = (c.file_path, c.start_line, c.end_line, c.content)
        previous = best_by_key.get(key)
        if previous is None or c.score > previous.score:
            best_by_key[key] = c
    unique_chunks = sorted(best_by_key.values(), key=lambda c: c.score, reverse=True)

    selected = []
    used = 0
    blocks = []
    for i, c in enumerate(unique_chunks, 1):
        content = c.content or "[content loaded from source database]"
        block = f"[S{i}] {c.file_path}:{c.start_line}-{c.end_line} | {c.chunk_type} | score={c.score:.4f}\n{content}\n"
        if used + len(block) > max_chars:
            continue
        blocks.append(block)
        selected.append(c)
        used += len(block)
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in (history or [])[-6:])
    user = f"QUESTION:\n{question}\n\n"
    if history_text: user += f"RECENT CONVERSATION:\n{history_text}\n\n"
    user += "RETRIEVED CONTEXT:\n" + ("\n".join(blocks) if blocks else "[NO RETRIEVED EVIDENCE]")
    return PromptBundle(SYSTEM, user, selected)
