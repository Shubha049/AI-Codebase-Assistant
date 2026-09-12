# Phase 9 — Interview Question Generator Verification

## Implemented
- Repository-specific interview question generation from actual symbols, dependency edges, and security findings.
- Difficulty and question-type selection.
- Structural/offline generation without requiring an LLM.
- Optional LLM enhancement through the existing provider abstraction.
- Persistent question sets with status and provenance.
- Repository-scoped APIs.
- Alembic migration.
- No new embedding or retrieval stack.

## API
- POST `/api/v1/repos/{repo_id}/interview/generate`
- GET `/api/v1/repos/{repo_id}/interview/latest`
- GET `/api/v1/repos/{repo_id}/interview/{set_id}`

## Verification
Python compilation and migration-chain inspection are performed as part of the Phase 9 implementation pass. Full runtime pytest verification depends on the environment's existing Phase 1–4 dependencies being installed; no unavailable dependency is represented as a successful test.

## Design safety
- Questions are derived from repository evidence.
- Structural mode does not require an LLM.
- LLM mode preserves source metadata and rejects malformed JSON.
- Mock LLM remains governed by the existing production configuration restrictions.
- Repository IDs are checked on every retrieval endpoint.

## Known limitations
- Structural questions are evidence-driven templates, not a full semantic assessment of developer skill.
- Real OpenAI/Ollama enhancement requires a reachable provider and valid configuration.
- No frontend UI is included in Phase 9.
