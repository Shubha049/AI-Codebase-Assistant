# Phase 6 — Architecture Explorer & Repository Visualization

## Implemented

- Architecture overview metrics from existing Phase 2/3 analysis data.
- File-level architecture graph with resolved intra-repository dependency edges.
- Isolated analyzed files are retained as graph nodes instead of disappearing from visualization.
- Node metadata: language, symbols, chunks, inbound/outbound dependencies.
- Edge weights for repeated dependency relationships.
- Configurable graph node cap to protect large repositories.
- File detail endpoint with symbols, imports, dependencies and dependents.
- Recursive dependency/dependent impact analysis with bounded depth.
- Reuses existing `DependencyEdge`, `CodeSymbol`, `ImportStatement`, and `Chunk` tables; no schema migration was necessary.

## API

- `GET /api/v1/repos/{repo_id}/architecture/overview`
- `GET /api/v1/repos/{repo_id}/architecture/graph?max_nodes=1000`
- `GET /api/v1/repos/{repo_id}/architecture/files/{file_path}`
- `GET /api/v1/repos/{repo_id}/architecture/impact?file_path=...&depth=2`

## Verification

- Python bytecode compilation: **passed** (`python -m compileall -q app tests`).
- Direct architecture-service smoke test with representative graph data: **passed**.
- Full pytest collection could not run in this environment because the existing project dependency `tree_sitter` is not installed. This is an environment dependency issue, not reported as a test pass.

## Design decisions

- Phase 6 does not duplicate dependency extraction. It consumes the dependency graph already produced by Phase 2.
- The graph contains isolated files because an architecture visualization should not silently hide modules with zero resolved internal edges.
- No frontend code is introduced in Phase 6. The API provides stable graph/file/impact data for the Phase 10 React frontend.
- No RAG/LLM calls are required for the architecture explorer.

## Known limitations

- Dependency edges are limited to imports that Phase 2 can resolve to an intra-repository file.
- Module/package-level semantic architecture is represented through file-level graph nodes; richer clustering can be added later without changing the core API.
- Large-graph visualization is capped through `max_nodes`; the response reports when truncation occurred.
