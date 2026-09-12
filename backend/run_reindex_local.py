import time
from app.db.session import SessionLocal
from app.db.models import Repository
from app.services.embedding_pipeline import run_embedding_pipeline
from app.config import get_settings

db = SessionLocal()
settings = get_settings()

print(f"Current Settings: EMBEDDING_PROVIDER={settings.embedding_provider}, EMBEDDING_MODEL={settings.embedding_model}")

repos = db.query(Repository).all()
print(f"Found {len(repos)} repositories in database.")

for r in repos:
    print(f"\n--- Re-indexing repo: {r.name} ({r.id}) ---")
    print(f"Initial: vector_count={r.vector_count}, provider={r.embedding_provider}, model={r.embedding_model}")
    t0 = time.perf_counter()
    run_embedding_pipeline(r.id, force=True)
    t1 = time.perf_counter()
    
    db.refresh(r)
    print(f"Completed in {t1-t0:.2f}s!")
    print(f"Updated: vector_count={r.vector_count}, status={r.status}, provider={r.embedding_provider}, model={r.embedding_model}")

db.close()
