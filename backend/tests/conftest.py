"""
Sets isolated environment variables BEFORE any `app.*` module is imported,
so the app's engine/settings never touch real ./data. conftest.py is
always loaded by pytest before sibling test modules, which is what makes
this ordering safe.
"""
import os
import tempfile
from pathlib import Path

_TEST_DIR = Path(tempfile.mkdtemp(prefix="aica_test_"))
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR / 'test.db'}"
os.environ["DATA_DIR"] = str(_TEST_DIR / "data")
os.environ["UPLOAD_TMP_DIR"] = str(_TEST_DIR / "data" / "tmp")
os.environ["REPO_STORAGE_DIR"] = str(_TEST_DIR / "data" / "repositories")
# Explicitly forced, not relied on as "just the class default" — Settings
# reads a real .env file when one exists (env_file=".env" in
# SettingsConfigDict), and .env.example correctly sets
# EMBEDDING_PROVIDER=local for real users per the README. Without this
# override, tests silently picked up whatever provider a developer's own
# .env happened to have — reproduced directly: `cp .env.example .env`
# followed by `pytest` made every embedding-pipeline test fail trying to
# load a real sentence-transformers model. Tests must be hermetic
# regardless of ambient files, not just work by coincidence when no .env
# is present.
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["QDRANT_URL"] = ":memory:"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from app.main import app  # noqa: E402
from app.core.auth import get_current_user  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import engine  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_alembic_cfg = Config(str(_REPO_ROOT / "alembic.ini"))
_alembic_cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))

TEST_USER_ID = "test-user-id"
TEST_USER_EMAIL = "test@example.com"


@pytest.fixture(autouse=True)
def _fresh_db():
    """Full alembic-managed reset before every test: downgrade to base,
    upgrade back to head. Deliberately NOT mixed with
    Base.metadata.drop_all() — that call doesn't touch Alembic's own
    `alembic_version` table, which left it stamped at head while the
    actual tables were gone, so upgrade() silently no-op'd on every test
    after the first. Letting Alembic own the full cycle avoids that."""
    command.downgrade(_alembic_cfg, "base")
    command.upgrade(_alembic_cfg, "head")
    with Session(engine) as db:
        user = User(
            id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            password_hash="scrypt$16384$8$1$dummy$dummy",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
    yield


@pytest.fixture
def test_user():
    return User(
        id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        password_hash="scrypt$16384$8$1$dummy$dummy",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


from app.services.auth import create_access_token  # noqa: E402


@pytest.fixture
def auth_token():
    return create_access_token(TEST_USER_ID, TEST_USER_EMAIL)


@pytest.fixture
def client(test_user, auth_token):
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app, headers={"Authorization": f"Bearer {auth_token}"}) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


