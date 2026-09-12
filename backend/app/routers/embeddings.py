from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, IndexingJob, JobStage
from app.db.session import get_db
from app.schemas.embeddings import (
    CollectionInfoResponse,
    EmbeddingStatusResponse,
    ReindexRequest,
    ReindexResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.services.embedding_pipeline import run_embedding_pipeline
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.factory import build_embedding_provider
from app.services.embeddings.retry import embed_batch_with_retry
from app.services.ingestion.repo_service import get_repository
from app.services.vectorstore.qdrant_store import (
    collection_info,
    collection_name_for_repo,
    delete_collection,
    get_qdrant_client,
    health_check,
    search as qdrant_search,
)

router = APIRouter(prefix="/api/v1/repos/{repo_id}/embeddings", tags=["embeddings"])


@router.get("/status", response_model=EmbeddingStatusResponse)
def get_embedding_status(repo_id: str, db: Session = Depends(get_db)):
    repo = get_repository(db, repo_id)  # 404 check
    latest_job = (
        db.query(IndexingJob)
        .filter(IndexingJob.repository_id == repo_id, IndexingJob.stage == JobStage.EMBEDDING)
        .order_by(IndexingJob.created_at.desc())
        .first()
    )
    return EmbeddingStatusResponse(
        repository_id=repo.id,
        status=repo.status.value,
        vector_count=repo.vector_count,
        embedding_provider=repo.embedding_provider,
        embedding_model=repo.embedding_model,
        embedding_dimension=repo.embedding_dimension,
        indexed_at=repo.indexed_at,
        job_status=latest_job.status if latest_job else None,
        job_progress_percent=latest_job.progress_percent if latest_job else None,
        job_message=latest_job.message if latest_job else None,
    )


@router.get("/collection", response_model=CollectionInfoResponse)
def get_collection(repo_id: str, db: Session = Depends(get_db)):
    get_repository(db, repo_id)  # 404 check
    settings = get_settings()
    client = get_qdrant_client(settings)
    if not health_check(client):
        raise HTTPException(status_code=503, detail="Qdrant is not reachable.")

    name = collection_name_for_repo(repo_id, settings.qdrant_collection_prefix)
    info = collection_info(client, name)
    if info is None:
        return CollectionInfoResponse(exists=False, collection_name=name)
    return CollectionInfoResponse(
        exists=True, collection_name=name,
        points_count=info["points_count"], vector_size=info["vector_size"], status=info["status"],
    )


@router.post("/reindex", status_code=202, response_model=ReindexResponse)
def reindex_repository(
    repo_id: str, body: ReindexRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
):
    repo = get_repository(db, repo_id)  # 404 check
    if repo.chunk_count == 0 or body.force:
        from app.services.chunk_generation_pipeline import run_chunking_pipeline
        background_tasks.add_task(run_chunking_pipeline, repo_id, body.force)
    else:
        background_tasks.add_task(run_embedding_pipeline, repo_id, body.force)
    return ReindexResponse(detail="Re-indexing started.", force=body.force)


@router.delete("", status_code=204)
def delete_repository_vectors(repo_id: str, db: Session = Depends(get_db)):
    repo = get_repository(db, repo_id)  # 404 check
    settings = get_settings()
    client = get_qdrant_client(settings)
    name = collection_name_for_repo(repo_id, settings.qdrant_collection_prefix)
    delete_collection(client, name)

    db.query(Chunk).filter(Chunk.repository_id == repo_id).update(
        {"embedded_at": None, "embedding_model": None}, synchronize_session=False,
    )
    repo.vector_count = 0
    repo.embedding_provider = None
    repo.embedding_model = None
    repo.embedding_dimension = None
    repo.indexed_at = None
    db.commit()


@router.post("/search", response_model=SearchResponse)
def search_similar_chunks(repo_id: str, body: SearchRequest, db: Session = Depends(get_db)):
    """
    Raw vector similarity search — returns matched chunks and their
    scores. No LLM, no answer synthesis (that's a later phase).
    """
    repo = get_repository(db, repo_id)  # 404 check
    settings = get_settings()
    provider = build_embedding_provider(settings)

    if repo.embedding_dimension is not None and repo.embedding_dimension != provider.dimension:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Repository was indexed with a {repo.embedding_dimension}-dimension model "
                f"({repo.embedding_provider}/{repo.embedding_model}), but the currently "
                f"configured provider produces {provider.dimension}-dimension vectors. "
                f"Re-index with the current provider (POST .../reindex?force=true) before searching."
            ),
        )

    try:
        query_vector = embed_batch_with_retry(provider, [body.query], settings.embedding_max_retries)[0]
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to embed query: {exc}") from exc

    client = get_qdrant_client(settings)
    name = collection_name_for_repo(repo_id, settings.qdrant_collection_prefix)
    hits = qdrant_search(client, name, query_vector, limit=body.top_k)

    # Single batched lookup instead of one query per hit (was an N+1
    # pattern — noticed by inspection, confirmed by counting queries
    # before fixing, see test_search_issues_single_db_query_not_n_plus_1).
    hit_ids = [str(hit.id) for hit in hits]
    content_by_id = {
        c.id: c.content
        for c in db.query(Chunk).filter(Chunk.id.in_(hit_ids))
    } if hit_ids else {}

    results = [
        SearchResultItem(
            chunk_id=str(hit.id),
            score=hit.score,
            file_path=hit.payload["file_path"],
            language=hit.payload["language"],
            chunk_type=hit.payload["chunk_type"],
            symbol_name=hit.payload.get("function_name"),
            parent_symbol_name=hit.payload.get("class_name"),
            start_line=hit.payload["start_line"],
            end_line=hit.payload["end_line"],
            content=content_by_id.get(str(hit.id), ""),
        )
        for hit in hits
    ]
    return SearchResponse(query=body.query, results=results)
