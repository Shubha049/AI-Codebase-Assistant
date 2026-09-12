# Phase 11 — Production Engineering Verification

## Implemented

- Authentication with registration/login and bearer access tokens.
- Password hashing using Python's scrypt implementation.
- Configurable token expiry and production auth secret validation.
- Repository ownership isolation for authenticated users.
- Protected `/api/v1/*` application APIs; health, docs, and authentication endpoints remain public.
- Production configuration validation: PostgreSQL required, mock embedding/LLM blocked, strong auth secret required, wildcard CORS blocked, public registration disabled.
- Security response headers.
- Request content-length guard using configured upload limit.
- `/ready` database readiness endpoint.
- PostgreSQL production driver.
- Docker Compose development stack with PostgreSQL, Qdrant, backend and frontend.
- Production Compose variant with restart policies and persistent volumes.
- Multi-stage frontend Docker build with Nginx SPA fallback.
- GitHub Actions CI for backend compilation/tests and frontend build.
- `.env.production.example` and root `.gitignore`.
- Alembic migration for users and repository ownership.

## Verified in this environment

- Python `compileall` for backend application and Alembic code: PASS.
- Python AST parsing of backend application, migrations and tests: PASS.

## Not live-verified

- Full pytest suite: not executed to completion because the sandbox is missing the existing project's runtime dependency chain and package installation is network constrained.
- Frontend Vite production build: not completed; `npm install` exceeded the execution timeout in this environment.
- Docker image builds: not executed because they require external image/package access.
- PostgreSQL/Qdrant live integration: not executed in the sandbox.
- Real OpenAI/Ollama calls: not executed.

## Production notes

1. Copy `backend/.env.production.example` to `backend/.env` and replace every placeholder.
2. Generate a high-entropy `AUTH_SECRET_KEY` and keep it outside source control.
3. Set `ALLOW_REGISTRATION=false` after the initial accounts are created.
4. Configure a real HTTPS reverse proxy/domain and set `CORS_ORIGINS` to the frontend origin.
5. Existing repositories created before Phase 11 have `owner_user_id=NULL`; they are intentionally inaccessible until explicitly assigned to an authenticated owner. This avoids accidentally exposing legacy data to a new account.
6. Run Alembic migrations before serving traffic. The included backend container runs `alembic upgrade head` before Uvicorn for the self-contained deployment path.
