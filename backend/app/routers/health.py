from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db.session import SessionLocal

router = APIRouter(tags=["health"])

@router.get("/health")
def health_check():
    settings = get_settings()
    return {"status": "ok", "app_name": settings.app_name, "environment": settings.environment}

@router.get("/ready")
def readiness_check():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(503, "Service is not ready.")
    finally:
        db.close()

@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi import Response
    return Response(status_code=204)

