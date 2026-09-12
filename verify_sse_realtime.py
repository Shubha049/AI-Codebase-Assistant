import io
import json
import zipfile
import httpx
import time

BASE_URL = "http://localhost:8000"

# 1. Create a sample repository ZIP
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("src/main.py", "from src.utils import helper\n\ndef run():\n    return helper('hello')\n")
    zf.writestr("src/utils.py", "def helper(name: str) -> str:\n    '''Helper function docstring'''\n    return f'processed {name}'\n")
    zf.writestr("src/models.py", "class DataModel:\n    '''Core entity model'''\n    def __init__(self, val: int):\n        self.val = val\n")
    zf.writestr("src/index.ts", "export const appName = 'TestApp';\nexport function calc(x: number): number { return x * 2; }\n")
    zf.writestr("README.md", "# Sample Live Test Repo\nThis is a real test repo for SSE validation.\n")
zip_bytes = buf.getvalue()

# 2. Authenticate
client = httpx.Client(base_url=BASE_URL, timeout=30.0)
email = f"live_test_{int(time.time())}@example.com"
password = "Password123!"

reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
if reg_resp.status_code == 201:
    token = reg_resp.json()["access_token"]
else:
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# 3. Upload repository
print(f"Uploading repository as {email}...")
t0 = time.perf_counter()
upload_resp = client.post(
    "/api/v1/repos/upload",
    files={"file": ("sample_live_repo.zip", zip_bytes, "application/zip")},
    headers=headers,
)
print(f"Upload response status: {upload_resp.status_code} (took {(time.perf_counter() - t0)*1000:.1f}ms)")
repo_data = upload_resp.json()
repo_id = repo_data["id"]
print(f"Assigned Repo ID: {repo_id}, Initial Status: {repo_data.get('status')}")

# 4. Stream SSE Events live
print(f"\nListening to live SSE event stream at /api/v1/repos/{repo_id}/events ...")
events_received = []

with client.stream("GET", f"/api/v1/repos/{repo_id}/events", headers=headers, timeout=60.0) as stream_resp:
    print(f"SSE Connection established: HTTP {stream_resp.status_code}")
    buffer = ""
    for chunk in stream_resp.iter_text():
        buffer += chunk
        lines = buffer.split("\n\n")
        buffer = lines.pop()
        for l in lines:
            if l.startswith("data: "):
                data = json.loads(l[6:])
                events_received.append(data)
                print(f"  [SSE Event] Status: {data.get('status'):<10} | Stage: {str(data.get('stage')):<18} | Progress: {data.get('progress_percent')}% | Files: {data.get('file_count')} | Symbols: {data.get('symbol_count')} | Chunks: {data.get('chunk_count')} | Vectors: {data.get('vector_count')}")
                if data.get("status") in ("indexed", "failed"):
                    break

print(f"\nTotal SSE event updates streamed: {len(events_received)}")
final_event = events_received[-1] if events_received else {}
print(f"Final state: Status={final_event.get('status')}, Vectors={final_event.get('vector_count')}, Chunks={final_event.get('chunk_count')}")

assert len(events_received) >= 1, "Should receive at least one SSE event"
assert final_event.get("status") == "indexed", f"Final status should be indexed, got {final_event.get('status')}"
print("\n>>> MANUAL SSE STREAM & ASYNC PIPELINE VERIFICATION: SUCCESS! <<<")
