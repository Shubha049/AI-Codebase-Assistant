import io
import zipfile


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# Deliberately includes an EXACT duplicate function body in two different
# files, to exercise real duplicate detection.
_DUP_FUNC = 'def shared_helper():\n    return 42\n'

_SAMPLE_REPO = {
    "myrepo/requirements.txt": "fastapi==0.115.0\n",
    "myrepo/app/main.py": (
        "class App:\n"
        '    """The application."""\n'
        "    def run(self):\n"
        "        return 1\n"
        "\n"
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


def test_chunking_summary_reflects_real_generated_chunks(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/chunks/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Phase 4 chains embedding immediately after chunking, so by the
    # time this request completes status has advanced to "ready".
    assert body["status"] == "ready"
    assert body["chunk_count"] > 0
    assert body["chunked_file_count"] == 2  # main.py, other.py (requirements.txt isn't code)
    assert body["job_status"] == "completed"
    assert body["job_progress_percent"] == 100


def test_exact_duplicate_function_across_files_is_detected(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/chunks")
    chunks = resp.json()["chunks"]

    shared_chunks = [c for c in chunks if c["symbol_name"] == "shared_helper"]
    assert len(shared_chunks) == 2

    duplicates = [c for c in shared_chunks if c["is_duplicate"]]
    canonicals = [c for c in shared_chunks if not c["is_duplicate"]]
    assert len(duplicates) == 1
    assert len(canonicals) == 1
    assert duplicates[0]["duplicate_of_chunk_id"] == canonicals[0]["id"]
    # Same content hash for both, obviously — that's WHY they're duplicates
    assert duplicates[0]["content_hash"] == canonicals[0]["content_hash"]


def test_non_duplicate_chunks_have_no_duplicate_reference(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/chunks")
    chunks = resp.json()["chunks"]
    unique_chunk = next(c for c in chunks if c["symbol_name"] == "unique_one")
    assert unique_chunk["is_duplicate"] is False
    assert unique_chunk["duplicate_of_chunk_id"] is None


def test_repository_duplicate_chunk_count_matches_actual_duplicates(client):
    repo_id = _upload_sample_repo(client)
    summary = client.get(f"/api/v1/repos/{repo_id}/chunks/summary").json()
    all_chunks = client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    actual_dupes = sum(1 for c in all_chunks if c["is_duplicate"])
    assert summary["duplicate_chunk_count"] == actual_dupes
    assert actual_dupes == 1


def test_exclude_duplicates_filter_works(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/chunks", params={"exclude_duplicates": True, "limit": 100})
    chunks = resp.json()["chunks"]
    assert all(not c["is_duplicate"] for c in chunks)
    shared = [c for c in chunks if c["symbol_name"] == "shared_helper"]
    assert len(shared) == 1  # only the canonical one


def test_chunk_content_matches_real_source_lines(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}/chunks", params={"file_path": "myrepo/app/main.py"})
    chunks = resp.json()["chunks"]
    run_chunk = next(c for c in chunks if c["symbol_name"] == "run")
    assert "return 1" in run_chunk["content"]
    assert run_chunk["parent_symbol_name"] == "App"
    assert run_chunk["chunk_type"] == "method"


def test_regenerate_without_force_skips_unchanged_files(client):
    repo_id = _upload_sample_repo(client)
    before = client.get(f"/api/v1/repos/{repo_id}/chunks/summary").json()
    before_chunk_ids = {
        c["id"] for c in client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    }

    resp = client.post(f"/api/v1/repos/{repo_id}/chunks/regenerate", params={"force": False})
    assert resp.status_code == 202

    after = client.get(f"/api/v1/repos/{repo_id}/chunks/summary").json()
    after_chunk_ids = {
        c["id"] for c in client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    }

    # Incremental indexing: nothing changed, so chunk IDs should be
    # UNTOUCHED (not deleted and regenerated with new IDs) — this is the
    # actual behavioral proof of "only changed files are reprocessed".
    assert before_chunk_ids == after_chunk_ids
    assert before["chunk_count"] == after["chunk_count"]


def test_regenerate_with_force_recreates_all_chunks(client):
    repo_id = _upload_sample_repo(client)
    before_chunk_ids = {
        c["id"] for c in client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    }

    resp = client.post(f"/api/v1/repos/{repo_id}/chunks/regenerate", params={"force": True})
    assert resp.status_code == 202

    after_chunk_ids = {
        c["id"] for c in client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 100}).json()["chunks"]
    }
    # force=True re-chunks everything -> brand new chunk rows (new IDs)
    assert before_chunk_ids.isdisjoint(after_chunk_ids)
    # but the same LOGICAL chunks should still exist (same count, same dedup outcome)
    summary = client.get(f"/api/v1/repos/{repo_id}/chunks/summary").json()
    assert summary["duplicate_chunk_count"] == 1


def test_chunks_endpoint_404_for_nonexistent_repo(client):
    for path in ["", "/summary"]:
        resp = client.get(f"/api/v1/repos/does-not-exist/chunks{path}")
        assert resp.status_code == 404


def test_chunk_type_breakdown_sums_to_total(client):
    repo_id = _upload_sample_repo(client)
    summary = client.get(f"/api/v1/repos/{repo_id}/chunks/summary").json()
    assert sum(summary["chunk_type_breakdown"].values()) == summary["chunk_count"]


def test_repository_overview_includes_phase3_chunk_fields(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}")
    body = resp.json()
    # Phase 4 chains embedding immediately after chunking, so by the
    # time this request completes status has advanced to "ready".
    assert body["status"] == "ready"
    assert body["chunk_count"] > 0
    assert body["duplicate_chunk_count"] == 1
    assert body["chunked_file_count"] == 2


def test_chunking_js_ts_repo_with_arrow_functions_classes_and_methods(client):
    """
    Verifies that a JS/TS repo containing arrow functions, classes with methods,
    and standalone functions indexes completely with no crashes and correct chunk types.
    """
    js_repo = {
        "tsrepo/package.json": '{"name": "tsrepo", "dependencies": {"react": "^18.0.0"}}',
        "tsrepo/src/index.ts": (
            "export const topLevelArrow = (x: number) => x * 2;\n\n"
            "export function standardFunc(name: string): string {\n"
            "    return `Hello, ${name}`;\n"
            "}\n"
        ),
        "tsrepo/src/Service.ts": (
            "export class DataService {\n"
            "    private endpoint: string;\n\n"
            "    constructor(endpoint: string) {\n"
            "        this.endpoint = endpoint;\n"
            "    }\n\n"
            "    fetchData() {\n"
            "        return this.endpoint;\n"
            "    }\n\n"
            "    handleCallback = (event: any) => {\n"
            "        console.log(event);\n"
            "    };\n"
            "}\n"
        ),
    }
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("tsrepo.zip", _make_zip(js_repo), "application/zip")},
    )
    assert resp.status_code == 201, resp.text
    repo_id = resp.json()["id"]

    # Retrieve summary
    summary_resp = client.get(f"/api/v1/repos/{repo_id}/chunks/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert summary["status"] == "ready"
    assert summary["job_status"] == "completed"
    assert summary["chunked_file_count"] == 2
    assert summary["chunk_count"] > 0

    # Retrieve chunks and verify valid ChunkTypes
    chunks_resp = client.get(f"/api/v1/repos/{repo_id}/chunks", params={"limit": 50})
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()["chunks"]
    valid_chunk_types = {
        "function", "method", "class", "class_header",
        "module_level", "function_window", "method_window",
        "file_window", "code_block", "unknown",
    }
    for c in chunks:
        assert c["chunk_type"] in valid_chunk_types

    # Specifically check the arrow function chunk in index.ts
    index_chunks = [c for c in chunks if c["file_path"] == "tsrepo/src/index.ts"]
    arrow_chunk = next(c for c in index_chunks if c["symbol_name"] == "topLevelArrow")
    assert arrow_chunk["chunk_type"] == "function"

