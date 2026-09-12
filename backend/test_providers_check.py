import urllib.request
import json

try:
    import sentence_transformers
    print("sentence_transformers: available (version", sentence_transformers.__version__, ")")
except ImportError as e:
    print("sentence_transformers: NOT installed (", e, ")")

try:
    req = urllib.request.Request("http://localhost:11434/api/tags", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        data = json.loads(resp.read().decode())
        print("Ollama running: available models ->", [m.get("name") for m in data.get("models", [])])
except Exception as e:
    print("Ollama check failed / not running on port 11434:", e)
