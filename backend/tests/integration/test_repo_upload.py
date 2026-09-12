import io
import zipfile


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_valid_zip_end_to_end(client):
    zip_bytes = _make_zip({
        "myrepo/main.py": "def hello():\n    return 'hi'\n",
        "myrepo/utils.py": "import os\n",
        "myrepo/README.md": "# My Repo\n",
        "myrepo/node_modules/pkg/index.js": "module.exports = {}\n",
    })

    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("myrepo.zip", zip_bytes, "application/zip")},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "scanned"
    assert body["file_count"] == 3  # node_modules excluded
    assert body["language_breakdown"]["Python"] == 2
    assert body["language_breakdown"]["Markdown"] == 1
    assert body["original_filename"] == "myrepo.zip"
    assert body["id"]  # a real id was assigned

    # And it's retrievable afterward
    get_resp = client.get(f"/api/v1/repos/{body['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == body["id"]


def test_upload_rejects_non_zip_file(client):
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("not_a_repo.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
    assert "zip" in resp.json()["detail"].lower()


def test_upload_rejects_zip_slip_path_traversal(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Classic zip-slip: entry name escapes the extraction directory.
        zf.writestr("../../etc/evil.py", "print('pwned')\n")
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("evil.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 400
    assert "unsafe" in resp.json()["detail"].lower()


def test_upload_rejects_corrupted_zip(client):
    resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("broken.zip", b"this is not actually a zip file", "application/zip")},
    )
    assert resp.status_code == 400


def test_list_repositories_after_multiple_uploads(client):
    zip_bytes = _make_zip({"repo/main.py": "x = 1\n"})
    for _ in range(3):
        client.post(
            "/api/v1/repos/upload",
            files={"file": ("r.zip", zip_bytes, "application/zip")},
        )

    resp = client.get("/api/v1/repos")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["repositories"]) == 3


def test_get_nonexistent_repository_returns_404(client):
    resp = client.get("/api/v1/repos/does-not-exist")
    assert resp.status_code == 404


def test_github_import_returns_honest_501(client):
    resp = client.post("/api/v1/repos/github", params={"url": "https://github.com/x/y"})
    assert resp.status_code == 501


def test_delete_repository(client):
    zip_bytes = _make_zip({"repo/main.py": "x = 1\n"})
    upload_resp = client.post(
        "/api/v1/repos/upload",
        files={"file": ("r.zip", zip_bytes, "application/zip")},
    )
    repo_id = upload_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/repos/{repo_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/repos/{repo_id}")
    assert get_resp.status_code == 404
