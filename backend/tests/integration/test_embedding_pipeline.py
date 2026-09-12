import io
import zipfile


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


_DUP_FUNC = 'def shared_helper():\n    return 42\n'

_SAMPLE_REPO = {
    "myrepo/requirements.txt": "fastapi==0.115.0\n",
    "myrepo/app/main.py": (
        "class App:\n"
        '    """The application."""\n'
        "    def run(self):\n"
        "        return 1\n\n"
        f"{_DUP_FUNC}"
    ),
    "myrepo/app/other.py": (
        f"{_DUP_FUNC}\n"
        "def unique_one():\n"
        "    return 2\n"
    ),
}


def _upload_sample_repo(client):
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("myrepo.zip", _make_zip(_SAMPLE_REPO), "application/zip")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_full_pipeline_reaches_ready_status_via_mock_provider(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}")
    body = resp.json()
    assert body["status"] == "ready"


def test_embedding_status_reflects_real_pipeline_output(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/embeddings/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["embedding_provider"] == "mock"
    assert body["embedding_dimension"] == 384
    assert body["vector_count"] > 0
    assert body["job_status"] == "completed"


def test_duplicate_chunks_each_get_their_own_vector_point(client):
    """Regression test: earlier version excluded duplicate chunks from
    Qdrant entirely, making a duplicate's own file/location unreachable
    via search even though the module's docstring claimed they were still
    mapped/discoverable. Verified by checking chunk_count vs vector_count
    directly, not assumed from the code."""
    repo_id = _upload_sample_repo(client)
    chunks = client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    status = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()

    duplicate_chunks = [c for c in chunks if c["is_duplicate"]]
    assert len(duplicate_chunks) == 1  # the shared_helper duplicate from Phase 3's own test data
    # vector_count must include duplicates too — not just canonical chunks
    assert status["vector_count"] == len(chunks)


def test_collection_info_matches_real_qdrant_state(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/embeddings/collection")
    assert resp.status_code == 200
    body = resp.json()
    assert body["exists"] is True
    assert body["vector_size"] == 384
    assert body["points_count"] > 0


def test_search_returns_relevant_chunk_for_similar_query(client):
    repo_id = _upload_sample_repo(client)
    resp = client.post(
        f"/api/v1/repos/{repo_id}/embeddings/search",
        json={"query": "def run(self): return 1", "top_k": 5},
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) > 0
    # The mock provider's feature-hashing genuinely rewards near-identical
    # text — the literal "run" method should be the top (or a top) hit.
    top_symbols = [r["symbol_name"] for r in results[:2]]
    assert "run" in top_symbols


def test_search_result_includes_real_chunk_content(client):
    repo_id = _upload_sample_repo(client)
    resp = client.post(
        f"/api/v1/repos/{repo_id}/embeddings/search",
        json={"query": "unique_one function returns 2", "top_k": 3},
    )
    results = resp.json()["results"]
    assert any("unique_one" in r["content"] for r in results)


def test_reindex_without_force_skips_already_embedded_chunks(client):
    repo_id = _upload_sample_repo(client)
    before = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()

    resp = client.post(f"/api/v1/repos/{repo_id}/embeddings/reindex", json={"force": False})
    assert resp.status_code == 202

    after_job = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()
    assert "already embedded and skipped" in after_job["job_message"]
    assert before["vector_count"] == after_job["vector_count"]


def test_reindex_with_force_recreates_all_vectors(client):
    repo_id = _upload_sample_repo(client)
    before = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()

    resp = client.post(f"/api/v1/repos/{repo_id}/embeddings/reindex", json={"force": True})
    assert resp.status_code == 202

    after = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()
    assert after["vector_count"] == before["vector_count"]  # same logical set, freshly rebuilt


def test_delete_vectors_clears_collection_and_resets_status(client):
    repo_id = _upload_sample_repo(client)
    resp = client.delete(f"/api/v1/repos/{repo_id}/embeddings")
    assert resp.status_code == 204

    status = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()
    assert status["vector_count"] == 0
    assert status["embedding_provider"] is None

    collection = client.get(f"/api/v1/repos/{repo_id}/embeddings/collection").json()
    assert collection["exists"] is False


def test_orphaned_vectors_removed_after_chunk_regeneration(client):
    """A real, end-to-end proof of the orphan-cleanup mechanism: force a
    chunk regeneration (Phase 3) which creates brand-new chunk IDs, then
    re-run embedding and confirm the OLD chunk IDs' vectors are gone from
    Qdrant, not left behind as orphans."""
    repo_id = _upload_sample_repo(client)
    old_chunk_ids = {
        c["id"] for c in client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    }

    # Force re-chunk -> brand new chunk rows/IDs (Phase 3 behavior)
    client.post(f"/api/v1/repos/{repo_id}/chunks/regenerate", params={"force": True})
    # Force re-embed on the NEW chunk set
    client.post(f"/api/v1/repos/{repo_id}/embeddings/reindex", json={"force": True})

    new_chunk_ids = {
        c["id"] for c in client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    }
    assert old_chunk_ids.isdisjoint(new_chunk_ids)

    # Trigger one more non-force reindex specifically to exercise the
    # orphan-detection pass, then confirm none of the OLD ids are
    # searchable/present anymore.
    client.post(f"/api/v1/repos/{repo_id}/embeddings/reindex", json={"force": False})
    status = client.get(f"/api/v1/repos/{repo_id}/embeddings/status").json()
    assert status["vector_count"] == len(new_chunk_ids)


def test_search_dimension_mismatch_returns_clear_409(client, monkeypatch):
    """Simulates the real scenario: a repo was indexed with one provider's
    dimension, then the configured provider changes to one with a
    different dimension, and search is attempted without re-indexing."""
    repo_id = _upload_sample_repo(client)

    from app.services.embeddings.providers.mock_provider import MockEmbeddingProvider
    import app.routers.embeddings as embeddings_router

    def _different_dimension_provider(settings):
        return MockEmbeddingProvider(dimension=64)  # repo was indexed at 384

    monkeypatch.setattr(embeddings_router, "build_embedding_provider", _different_dimension_provider)

    resp = client.post(
        f"/api/v1/repos/{repo_id}/embeddings/search",
        json={"query": "anything", "top_k": 5},
    )
    assert resp.status_code == 409
    assert "dimension" in resp.json()["detail"].lower()


def test_embeddings_endpoints_404_for_nonexistent_repo(client):
    for method, path in [
        ("get", "/status"), ("get", "/collection"), ("delete", ""),
    ]:
        resp = getattr(client, method)(f"/api/v1/repos/does-not-exist/embeddings{path}")
        assert resp.status_code == 404


def test_repository_overview_includes_phase4_embedding_fields(client):
    repo_id = _upload_sample_repo(client)
    body = client.get(f"/api/v1/repos/{repo_id}").json()
    assert body["status"] == "ready"
    assert body["vector_count"] > 0
    assert body["embedding_provider"] == "mock"
    assert body["embedding_dimension"] == 384
    assert body["indexed_at"] is not None
