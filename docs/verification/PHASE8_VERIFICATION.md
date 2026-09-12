# Phase 8 — Documentation Generator Verification

## Implemented

- Structural Markdown documentation generated from persisted repository analysis.
- Repository overview, detected frameworks/build systems, language counts, repository tree, architecture centrality, file/module table, symbols, imports, and documentation limitations.
- Optional LLM refinement using the existing provider abstraction. The LLM is never required for the deterministic documentation path.
- Documentation artifacts persisted in the database.
- Background generation API with polling.
- Repository-scoped artifact retrieval; cross-repository artifact access returns 404.
- Alembic migration for documentation artifacts.

## API

- `POST /api/v1/repos/{repo_id}/documentation/generate`
- `GET /api/v1/repos/{repo_id}/documentation/latest`
- `GET /api/v1/repos/{repo_id}/documentation/{artifact_id}`

## Verification performed

- `python -m compileall -q app alembic` completed successfully before runtime import checks.
- Source-level inspection confirms the new model, migration, service, schemas, router, and main-router registration are syntactically integrated.
- Runtime route import could not be completed in this environment because the existing project dependency `tree_sitter` is not installed. This is an environment dependency issue inherited from the supplied Phase 7 project, not a claim of a passing application test suite.

## LLM verification

The deterministic documentation generator does not require an LLM.

Optional OpenAI/Ollama refinement is implemented through the existing provider layer but is **not claimed as live-verified** without a reachable configured provider.

## Real bug found and fixed while carrying forward Phase 7

`app/routers/security.py` scheduled its background task using `scan.id` before `scan` was created. The order was corrected so the pending scan row is created, committed, and then scheduled.

## Known limitations

- Documentation is structural unless `use_llm=true` is requested.
- The generator does not execute repository code.
- It does not claim undocumented business behavior as fact.
- The file table is capped at 500 rows for document size; complete data remains available through analysis APIs.
- Full runtime/pytest verification remains blocked by the missing `tree_sitter` dependency in this execution environment.
