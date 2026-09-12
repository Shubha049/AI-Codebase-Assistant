import io
import zipfile


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# A small, realistic multi-language repo: Python backend with an internal
# import, TypeScript frontend with a relative import, and a requirements.txt
# / package.json so framework detection has something real to find.
_SAMPLE_REPO = {
    "myrepo/requirements.txt": "fastapi==0.115.0\n",
    "myrepo/app/main.py": (
        "from app.config import get_settings\n\n"
        "class App:\n"
        '    """The application."""\n'
        "    def run(self):\n"
        "        return get_settings()\n"
    ),
    "myrepo/app/config.py": (
        "def get_settings():\n"
        "    return {}\n"
    ),
    "myrepo/frontend/package.json": '{"dependencies": {"react": "^18.3.1"}}',
    "myrepo/frontend/src/App.tsx": (
        'import { helper } from "./utils";\n\n'
        "export class Widget {\n"
        "    render() {\n"
        "        return helper();\n"
        "    }\n"
        "}\n"
    ),
    "myrepo/frontend/src/utils.ts": (
        "export function helper() {\n    return 1;\n}\n"
    ),
}


def _upload_sample_repo(client):
    zip_bytes = _make_zip(_SAMPLE_REPO)
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("myrepo.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_upload_response_still_reports_scanned_not_analyzed(client):
    """
    The immediate upload response must still reflect the Phase 1 contract
    (status='scanned') — analysis happens in the background AFTER the
    response is serialized. This is what makes Phase 2 non-breaking for
    Phase 1 consumers.
    """
    zip_bytes = _make_zip(_SAMPLE_REPO)
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("myrepo.zip", zip_bytes, "application/zip")},
    )
    assert resp.json()["status"] == "scanned"


def test_analysis_summary_reflects_real_parsed_data(client):
    repo_id = _upload_sample_repo(client)

    resp = client.get(f"/api/v1/repos/{repo_id}/analysis/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Phase 3 chains chunking, Phase 4 chains embedding, immediately
    # after analysis — by the time this request completes (TestClient
    # runs background tasks synchronously) status has advanced all the
    # way to "ready". Analysis fields below are still exactly what
    # Phase 2 produced.
    assert body["status"] == "ready"
    assert body["symbol_count"] > 0
    assert body["parsed_file_count"] == 4  # main.py, config.py, App.tsx, utils.ts
    assert "FastAPI" in body["frameworks"]
    assert "React" in body["frameworks"]
    assert "pip" in body["build_systems"]
    assert "npm" in body["build_systems"]
    assert body["dependency_edge_count"] >= 2  # main->config, App.tsx->utils.ts
    assert body["latest_job"]["status"] == "completed"
    assert body["latest_job"]["progress_percent"] == 100


def test_symbols_endpoint_returns_real_extracted_entities(client):
    repo_id = _upload_sample_repo(client)

    resp = client.get(f"/api/v1/repos/{repo_id}/analysis/symbols")
    assert resp.status_code == 200
    body = resp.json()
    names = {s["name"] for s in body["symbols"]}
    assert {"App", "run", "get_settings", "Widget", "render", "helper"} <= names

    # Verify a specific symbol's metadata is accurate, not just present
    app_class = next(s for s in body["symbols"] if s["name"] == "App")
    assert app_class["symbol_type"] == "class"
    assert app_class["docstring"] == "The application."
    assert app_class["file_path"] == "myrepo/app/main.py"

    run_method = next(s for s in body["symbols"] if s["name"] == "run")
    assert run_method["symbol_type"] == "method"
    assert run_method["parent_name"] == "App"


def test_symbols_endpoint_filters_by_file_path(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(
        f"/api/v1/repos/{repo_id}/analysis/symbols",
        params={"file_path": "myrepo/app/config.py"},
    )
    body = resp.json()
    assert all(s["file_path"] == "myrepo/app/config.py" for s in body["symbols"])
    assert any(s["name"] == "get_settings" for s in body["symbols"])


def test_dependency_graph_reflects_real_resolved_imports(client):
    repo_id = _upload_sample_repo(client)

    resp = client.get(f"/api/v1/repos/{repo_id}/analysis/dependency-graph")
    assert resp.status_code == 200
    body = resp.json()

    edges = {(e["source_file"], e["target_file"]) for e in body["edges"]}
    assert ("myrepo/app/main.py", "myrepo/app/config.py") in edges
    assert ("myrepo/frontend/src/App.tsx", "myrepo/frontend/src/utils.ts") in edges
    assert "myrepo/app/main.py" in body["nodes"]


def test_analysis_endpoints_404_for_nonexistent_repo(client):
    for path in ["summary", "symbols", "dependency-graph"]:
        resp = client.get(f"/api/v1/repos/does-not-exist/analysis/{path}")
        assert resp.status_code == 404


def test_repository_overview_includes_phase2_fields_after_analysis(client):
    repo_id = _upload_sample_repo(client)
    resp = client.get(f"/api/v1/repos/{repo_id}")
    body = resp.json()
    # Phase 3 chains chunking, Phase 4 chains embedding — see comment in
    # the summary test above for why "ready" is correct here.
    assert body["status"] == "ready"
    assert body["symbol_count"] > 0
    assert "FastAPI" in body["frameworks"]
