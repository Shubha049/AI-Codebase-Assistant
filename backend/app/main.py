import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.db.models import Repository
from app.db.session import SessionLocal
from app.services.auth import decode_access_token

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter
from app.config import get_settings
from app.core.exceptions import AICAException
from app.logging_config import configure_logging
from app.routers import analysis, architecture, chunks, documentation, embeddings, health, repos, qa, security, interview, auth



class AuthMiddleware(BaseHTTPMiddleware):
    """Require bearer authentication for application APIs and enforce repository ownership.

    Health/docs/auth endpoints remain public. Repository ownership is checked at the
    edge for all /repos/{repo_id}/... routes, while body-scoped QA ownership is checked
    by the QA route itself.
    """
    PUBLIC_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/")

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if path in self.PUBLIC_PREFIXES or any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Authentication required."}, headers={"WWW-Authenticate": "Bearer"})
        try:
            payload = decode_access_token(auth.split(" ", 1)[1].strip())
            request.state.user_id = payload["sub"]
            request.state.user_email = payload.get("email")
        except ValueError:
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired access token."}, headers={"WWW-Authenticate": "Bearer"})

        parts = [p for p in path.split("/") if p]
        # /api/v1/repos/{repo_id}/...
        if len(parts) >= 4 and parts[0:3] == ["api", "v1", "repos"]:
            repo_id = parts[3]
            # Collection operations /repos and /repos/upload have no repository id.
            if repo_id not in {"upload", "github"}:
                db: Session = SessionLocal()
                try:
                    repo = db.get(Repository, repo_id)
                    if not repo or repo.owner_user_id != request.state.user_id:
                        return JSONResponse(status_code=404, content={"detail": "Repository not found."})
                finally:
                    db.close()
        return await call_next(request)



class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.environment == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"} and request.headers.get("content-length"):
            limit = get_settings().max_upload_size_mb * 1024 * 1024 + 1024 * 1024
            if int(request.headers["content-length"]) > limit:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds configured size limit."})
        return await call_next(request)

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment == "production":
        settings.validate_for_production()

    # Schema is owned entirely by Alembic — run `alembic upgrade head`
    # before starting the server (see README / Dockerfile CMD). No
    # create_all() fallback here: mixing the two silently caused
    # "table already exists" failures the moment someone ran a migration
    # after the app had already auto-created tables once. One source of
    # truth for schema, not two that can disagree.
    logger.info(
        "%s starting up | env=%s | db=%s",
        settings.app_name, settings.environment, settings.database_url,
    )

    if settings.llm_provider == "ollama":
        import asyncio
        import httpx

        async def _warmup_ollama():
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    await client.post(
                        f"{settings.ollama_url.rstrip('/')}/api/chat",
                        json={
                            "model": settings.llm_model_name,
                            "messages": [{"role": "user", "content": "hi"}],
                            "keep_alive": settings.ollama_keep_alive,
                            "options": {"num_predict": 1},
                        },
                    )
                logger.info(
                    "Ollama model '%s' warmed up and pinned in RAM (keep_alive=%s).",
                    settings.llm_model_name,
                    settings.ollama_keep_alive,
                )
            except Exception as exc:
                logger.warning("Ollama warmup skipped / non-critical: %s", exc)

        asyncio.create_task(_warmup_ollama())

    yield
    logger.info("%s shutting down.", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Repository intelligence backend — see /docs for the API.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if settings.environment != "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AICAException)
async def aica_exception_handler(request: Request, exc: AICAException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(repos.router)
app.include_router(analysis.router)
app.include_router(chunks.router)
app.include_router(embeddings.router)
app.include_router(qa.router)
app.include_router(architecture.router)
app.include_router(security.router)
app.include_router(documentation.router)
app.include_router(interview.router)
