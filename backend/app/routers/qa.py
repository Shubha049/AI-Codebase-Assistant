import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import get_current_user
from app.core.limiter import limiter
from app.db.models import User
from app.db.models import Chunk, Conversation, ConversationMessage, Repository, RepoStatus
from app.db.session import get_db
from app.schemas.qa import AskRequest, QAResponse, Citation, RetrievedChunkResponse
from app.services.llm import LLMError, build_llm_provider
from app.services.rag.confidence import confidence
from app.services.rag.prompt_builder import build_prompt
from app.services.rag.retrieval import RetrievedChunk, retrieve

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])


def _history(db: Session, conversation_id: str | None, repo_id: str):
    if not conversation_id:
        return None, []
    convo = db.get(Conversation, conversation_id)
    if not convo or convo.repository_id != repo_id:
        raise HTTPException(404, "Conversation not found for this repository.")
    return convo, [{"role": m.role, "content": m.content} for m in convo.messages[-10:]]


def _content_by_id(db: Session, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {c.id: c.content for c in db.query(Chunk).filter(Chunk.id.in_(ids)).all()}


def _with_content(chunks: list[RetrievedChunk], contents: dict[str, str]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            c.chunk_id, c.score, c.repository_id, c.repository_name, c.file_path,
            c.language, c.module, c.class_name, c.function_name, c.chunk_type,
            c.start_line, c.end_line, contents.get(c.chunk_id, ""),
        )
        for c in chunks
        if contents.get(c.chunk_id, "")
    ]


def _prepare(body: AskRequest, db: Session, user: User):
    started = time.perf_counter()
    repo = db.get(Repository, body.repository_id)
    if repo and repo.owner_user_id != user.id:
        repo = None
    if not repo:
        raise HTTPException(404, "Repository not found.")
    if repo.status != RepoStatus.READY or not repo.vector_count:
        if repo.status == RepoStatus.FAILED:
            msg = f"Repository indexing failed: {repo.error_message or 'Unknown error'}. Please re-index it."
        elif repo.status in (RepoStatus.UPLOADING, RepoStatus.EXTRACTING, RepoStatus.SCANNING, RepoStatus.SCANNED, RepoStatus.PARSING, RepoStatus.ANALYZED, RepoStatus.CHUNKING, RepoStatus.CHUNKED, RepoStatus.INDEXING):
            msg = f"Repository indexing is in progress (stage: {repo.status.value}). Wait for indexing to complete."
        elif repo.status == RepoStatus.READY and not repo.vector_count:
            msg = "Repository has 0 searchable vectors. Ensure the repository contains analyzable source files and re-index it."
        else:
            msg = f"Repository is not ready for querying (status: {repo.status.value}, vectors: {repo.vector_count}). Please wait or re-index."
        raise HTTPException(409, msg)

    settings = get_settings()
    convo, history = _history(db, body.conversation_id, repo.id)
    f = body.filters
    try:
        chunks = retrieve(
            repo.id,
            body.question,
            settings,
            top_k=body.top_k,
            threshold=body.similarity_threshold,
            language=f.language if f else None,
            file_path=f.file_path if f else None,
            class_name=f.class_name if f else None,
            function_name=f.function_name if f else None,
        )
        contents = _content_by_id(db, [c.chunk_id for c in chunks])
        chunks = _with_content(chunks, contents)
        bundle = build_prompt(body.question, chunks, history)
        # No evidence is a valid terminal RAG state; do not require an LLM
        # provider just to return the grounded "insufficient evidence" answer.
        provider = build_llm_provider(settings) if bundle.chunks else None
    except (RuntimeError, LLMError) as exc:
        raise HTTPException(502, str(exc)) from exc

    return started, repo, convo, history, bundle, provider


def _save_turn(db: Session, repo: Repository, convo: Conversation | None, question: str, answer: str) -> Conversation:
    if convo is None:
        convo = Conversation(repository_id=repo.id, title=question[:255])
        db.add(convo)
        db.flush()
    db.add(ConversationMessage(conversation_id=convo.id, role="user", content=question))
    db.add(ConversationMessage(conversation_id=convo.id, role="assistant", content=answer))
    db.commit()
    return convo


def _response(started, repo, convo, body, bundle, provider, answer):
    convo_id = convo.id if convo else ""
    cites = [
        Citation(source_id=f"S{i}", repository=repo.name, file=c.file_path, chunk_id=c.chunk_id,
                 start_line=c.start_line, end_line=c.end_line, similarity_score=c.score)
        for i, c in enumerate(bundle.chunks, 1)
    ]
    retrieved = [
        RetrievedChunkResponse(chunk_id=c.chunk_id, file_path=c.file_path, start_line=c.start_line,
                               end_line=c.end_line, similarity_score=c.score, content=c.content)
        for c in bundle.chunks
    ]
    settings = get_settings()
    return QAResponse(
        conversation_id=convo_id,
        answer=answer,
        sources=cites,
        confidence=confidence(
            [c.score for c in bundle.chunks],
            provider_name=settings.embedding_provider,
            threshold=body.similarity_threshold,
        ),
        retrieved_chunks=retrieved,
        processing_time_ms=int((time.perf_counter() - started) * 1000),
        llm_provider=provider.provider_name if provider else "none",
        llm_model=provider.model_name if provider else "none",
    )


@router.post("/ask", response_model=QAResponse)
@limiter.limit("30/minute")
def ask(
    request: Request,
    body: AskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started, repo, convo, history, bundle, provider = _prepare(body, db, user)

    if not bundle.chunks:
        answer = "I don't have sufficient repository evidence to answer that question."
        convo = _save_turn(db, repo, convo, body.question, answer)
        return _response(started, repo, convo, body, bundle, provider, answer)

    if body.stream:
        def generate_ndjson() -> Iterator[str]:
            pieces: list[str] = []
            try:
                for delta in provider.stream(bundle.system_prompt, bundle.user_prompt, history):
                    if not delta:
                        continue
                    pieces.append(delta)
                    yield json.dumps({"delta": delta}) + "\n"
                answer = "".join(pieces)
                if not answer:
                    raise LLMError("LLM returned an empty streaming response")
                saved = _save_turn(db, repo, convo, body.question, answer)
                metadata = _response(started, repo, saved, body, bundle, provider, answer)
                yield json.dumps({"done": True, "response": metadata.model_dump()}) + "\n"
            except LLMError as exc:
                db.rollback()
                yield json.dumps({"error": str(exc)}) + "\n"
            finally:
                db.close()

        return StreamingResponse(generate_ndjson(), media_type="application/x-ndjson")

    try:
        answer = provider.generate(bundle.system_prompt, bundle.user_prompt, history).text
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not answer.strip():
        raise HTTPException(502, "LLM returned an empty response.")
    convo = _save_turn(db, repo, convo, body.question, answer)
    return _response(started, repo, convo, body, bundle, provider, answer)
