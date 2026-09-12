import json
import time
import zipfile
import io
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def log(msg):
    print(f"[TEST] {msg}")

def request(path, method="GET", data=None, headers=None):
    url = f"{BASE_URL}{path}"
    headers = headers or {}
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, bytes):
            body = data
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content = resp.read()
            if status == 204 or not content:
                return status, None
            try:
                return status, json.loads(content.decode("utf-8"))
            except Exception:
                return status, content.decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, err_body

def main():
    log("1. Checking /health endpoint...")
    status, res = request("/health")
    assert status == 200, f"Health check failed: {status} {res}"
    log(f"-> /health OK: {res}")

    log("2. Checking /docs endpoint...")
    status, res = request("/docs")
    assert status == 200, f"/docs failed: {status}"
    log("-> /docs OK (200)")

    test_email = f"dev_{int(time.time())}@example.com"
    test_pass = "TestPassword123!"

    log(f"3. Testing Registration for {test_email}...")
    status, res = request("/api/v1/auth/register", method="POST", data={"email": test_email, "password": test_pass})
    assert status in (200, 201), f"Registration failed: {status} {res}"
    token = res["access_token"]
    user_id = res["user"]["id"]
    log(f"-> Register OK: user_id={user_id}, token={token[:16]}...")

    log("4. Testing Login...")
    status, res = request("/api/v1/auth/login", method="POST", data={"email": test_email, "password": test_pass})
    assert status == 200, f"Login failed: {status} {res}"
    token = res["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    log("-> Login OK")

    log("5. Testing /api/v1/auth/me...")
    status, res = request("/api/v1/auth/me", headers=auth_headers)
    assert status == 200 and res["email"] == test_email, f"/me failed: {status} {res}"
    log(f"-> /me OK: {res}")

    log("6. Testing Repository Upload...")
    # Create an in-memory zip file containing a Python module and JS module
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app/main.py", "def add(a, b):\n    return a + b\n\nclass Calculator:\n    def multiply(self, x, y):\n        return x * y\n")
        zf.writestr("app/auth.py", "import hashlib\n\ndef hash_pw(pw):\n    return hashlib.sha256(pw.encode()).hexdigest()\n")
        zf.writestr("frontend/index.js", "import { add } from './app';\nconsole.log(add(2, 3));\n")
        zf.writestr("package.json", '{"name": "demo-app", "dependencies": {"express": "^4.18.2"}}\n')
        zf.writestr("requirements.txt", "fastapi==0.110.0\nuvicorn==0.28.0\n")

    zip_bytes = zip_buffer.getvalue()
    boundary = "----WebKitFormBoundaryE2ETestBoundary123"
    body_lines = [
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="file"; filename="demo-repo.zip"',
        b"Content-Type: application/zip",
        b"",
        zip_bytes,
        f"--{boundary}--".encode(),
        b""
    ]
    multipart_body = b"\r\n".join(body_lines)
    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }

    status, repo = request("/api/v1/repos/upload", method="POST", data=multipart_body, headers=upload_headers)
    assert status == 201, f"Upload failed: {status} {repo}"
    repo_id = repo["id"]
    log(f"-> Upload OK: repo_id={repo_id}, name={repo['name']}, status={repo['status']}")

    log("7. Waiting for background pipeline (analysis -> chunking -> embedding)...")
    for _ in range(30):
        time.sleep(1)
        status, cur_repo = request(f"/api/v1/repos/{repo_id}", headers=auth_headers)
        if cur_repo["status"] in ("ready", "analyzed", "chunked"):
            log(f"-> Repo Pipeline state: status={cur_repo['status']}, parsed_files={cur_repo['parsed_file_count']}, symbols={cur_repo['symbol_count']}, chunks={cur_repo['chunk_count']}, vectors={cur_repo['vector_count']}")
            if cur_repo["status"] == "ready" and cur_repo["vector_count"] > 0:
                break

    log("8. Testing Analysis Summary...")
    status, analysis = request(f"/api/v1/repos/{repo_id}/analysis/summary", headers=auth_headers)
    assert status == 200, f"Analysis summary failed: {status} {analysis}"
    log(f"-> Analysis summary: frameworks={analysis['frameworks']}, symbols={analysis['symbol_count']}, edges={analysis['dependency_edge_count']}")

    log("9. Testing Architecture Overview & Graph...")
    status, arch_overview = request(f"/api/v1/repos/{repo_id}/architecture/overview", headers=auth_headers)
    assert status == 200, f"Arch overview failed: {status}"
    status, arch_graph = request(f"/api/v1/repos/{repo_id}/architecture/graph", headers=auth_headers)
    assert status == 200, f"Arch graph failed: {status}"
    log(f"-> Arch Graph OK: total_nodes={arch_graph['total_nodes']}, total_edges={arch_graph['total_edges']}")

    log("10. Testing Security Scanner...")
    status, scan = request(f"/api/v1/repos/{repo_id}/security/scan", method="POST", headers=auth_headers)
    assert status in (200, 202), f"Security scan failed: {status}"
    time.sleep(1.5)
    status, sec_summary = request(f"/api/v1/repos/{repo_id}/security/summary", headers=auth_headers)
    assert status == 200, f"Security summary failed: {status}"
    log(f"-> Security summary OK: total_findings={sec_summary['total_findings']}, latest_scan_status={sec_summary.get('latest_scan', {}).get('status')}")

    log("11. Testing Documentation Generator...")
    status, doc_gen = request(f"/api/v1/repos/{repo_id}/documentation/generate", method="POST", data={"use_llm": False}, headers=auth_headers)
    assert status in (200, 202), f"Docs generate failed: {status}"
    time.sleep(1.5)
    status, doc_latest = request(f"/api/v1/repos/{repo_id}/documentation/latest", headers=auth_headers)
    assert status == 200 and doc_latest is not None, f"Docs latest failed: {status}"
    log(f"-> Docs generation OK: status={doc_latest['status']}, format={doc_latest['format']}, length={len(doc_latest.get('content') or '')}")

    log("12. Testing Interview Generator...")
    status, int_gen = request(f"/api/v1/repos/{repo_id}/interview/generate", method="POST", data={"count": 5, "difficulty": "medium", "use_llm": False}, headers=auth_headers)
    assert status in (200, 202), f"Interview generate failed: {status}"
    time.sleep(1.5)
    status, int_latest = request(f"/api/v1/repos/{repo_id}/interview/latest", headers=auth_headers)
    assert status == 200 and int_latest is not None, f"Interview latest failed: {status}"
    log(f"-> Interview generation OK: questions_count={len(int_latest.get('questions') or [])}")

    log("13. Testing Grounded Q&A...")
    status, qa_res = request("/api/v1/qa/ask", method="POST", data={
        "repository_id": repo_id,
        "question": "How does the Calculator class work?",
        "top_k": 5,
        "similarity_threshold": 0.0
    }, headers=auth_headers)
    assert status == 200, f"QA failed: {status} {qa_res}"
    log(f"-> Grounded Q&A OK: answer='{qa_res['answer'][:60]}...', citations={len(qa_res['sources'])}, confidence={qa_res['confidence']}")

    log("\n=======================================================")
    log("ALL 13 END-TO-END VERIFICATION STEPS PASSED PERFECTLY!")
    log("=======================================================\n")

if __name__ == "__main__":
    main()
