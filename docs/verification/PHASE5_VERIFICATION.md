# Phase 5 — RAG & AI Question Answering

## Implemented

- Qdrant semantic retrieval with top-K, similarity threshold, and repository/language/file/class/function filters.
- Dedicated prompt builder with bounded context, metadata, line ranges and citation IDs.
- Exact duplicate-context suppression that retains the **highest-scoring** duplicate.
- LLM provider abstraction with OpenAI, Ollama and an offline-only Mock provider.
- `POST /api/v1/qa/ask` with answer, sources, confidence, retrieved chunks and processing time.
- Persistent conversation and message storage through an Alembic migration.
- Native provider streaming for OpenAI SSE and Ollama NDJSON, exposed as NDJSON from the QA endpoint.
- Provider HTTP status handling while the streaming response context is still open.
- Explicit no-evidence / no-index / provider error handling.
- Production guard preventing the Mock LLM provider.
- Repository-scoped conversation validation and retrieval isolation.

## Verification status

### Actually verified in this environment

- `python -m compileall -q app tests` completed successfully after the Phase 5 hardening pass.
- Static contract checks confirmed the QA router, retrieval filters, highest-score deduplication logic, and all three LLM providers are present.

### Test suite limitation

A real `pytest` run was attempted. Collection stopped before tests could execute because the execution environment does not contain the project's required `tree_sitter` dependency:

`ModuleNotFoundError: No module named 'tree_sitter'`

`qdrant-client` is also not installed in the execution environment. Therefore **no pytest pass count is claimed** and the FastAPI/Qdrant integration is **not claimed as executed here**.

The previous Phase 4 project verification reported 157/157 tests passing, but that result is not re-used as a Phase 5 test result.

### Implemented but not live-verified

- OpenAI LLM generation and streaming: requires a reachable OpenAI API and valid `LLM_API_KEY`.
- Ollama generation and streaming: requires a reachable Ollama server and installed model.
- Real Qdrant indexing/retrieval: requires `qdrant-client` in the runtime environment.
- Full FastAPI end-to-end QA flow: requires the project's dependencies to be installed.
- Real semantic answer quality: requires a real embedding provider and LLM.

The Mock LLM remains an offline/test provider and is rejected when `ENVIRONMENT=production`.

## Local verification

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
pytest -v
uvicorn app.main:app --reload --port 8000
```

For offline verification:

```env
ENVIRONMENT=test
EMBEDDING_PROVIDER=mock
LLM_PROVIDER=mock
QDRANT_URL=:memory:
```

For OpenAI:

```env
LLM_PROVIDER=openai
LLM_API_KEY=<your-key>
LLM_MODEL_NAME=<model>
```

For Ollama:

```env
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL_NAME=<installed-model>
```

## Bugs found and fixed in the final pass

1. Prompt deduplication could retain the first duplicate instead of the highest-scoring duplicate. It now selects the strongest-scoring occurrence before assigning citation IDs.
2. Streaming HTTP status/body handling is performed while the response context manager remains open.
3. The QA endpoint previously simulated streaming by calling the non-streaming LLM method and splitting the final answer. It now uses the provider's native `stream()` interface when `stream=true`.
4. A repository with no retrieved evidence no longer requires an LLM provider just to return the grounded insufficient-evidence response.
5. Streaming now persists the completed conversation turn only after the provider stream has completed successfully.
6. Empty streaming responses are treated as provider failures rather than successful answers.

## Known limitations

- Full automated Phase 5 execution could not be performed in this environment because required dependencies are unavailable.
- No provider failover is implemented.
- Conversation history is intentionally limited to the most recent messages supplied to the prompt.
- The current streaming API emits answer deltas followed by a final metadata object; clients must handle NDJSON rather than the normal `QAResponse` JSON shape.
