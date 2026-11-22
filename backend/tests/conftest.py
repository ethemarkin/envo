"""Test setup: a real PostgreSQL database (envo_test) migrated with Alembic.

Requires the docker compose `db` service. Override the URL with
ENVO_TEST_DATABASE_URL if the database lives elsewhere.
"""

import asyncio
import os
import uuid
from pathlib import Path

os.environ["ENVO_DATABASE_URL"] = os.environ.get(
    "ENVO_TEST_DATABASE_URL", "postgresql+asyncpg://envo:envo@localhost:5432/envo_test"
)
os.environ["ENVO_SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["ENVO_COOKIE_SECURE"] = "false"
os.environ["ENVO_GOOGLE_CLIENT_ID"] = ""
os.environ["ENVO_GOOGLE_CLIENT_SECRET"] = ""
# Fixed test-only master key (32 bytes, base64).
os.environ["ENVO_MASTER_KEY"] = "dGVzdC1tYXN0ZXIta2V5LTMyLWJ5dGVzLWxvbmchISE="
os.environ["ENVO_MASTER_KEY_ID"] = "test1"
os.environ["ENVO_RETIRED_MASTER_KEYS"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.authorization.policy import Role  # noqa: E402
from app.modules.organizations.models import Membership  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
TABLES = [
    "audit_events",
    "variable_revisions",
    "environment_revisions",
    "variables",
    "environments",
    "projects",
    "memberships",
    "organizations",
    "refresh_tokens",
    "user_identities",
    "users",
]


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = os.environ["ENVO_DATABASE_URL"]
    # env.py calls asyncio.run(), so it must run outside this event loop.
    await asyncio.to_thread(command.upgrade, cfg, "head")
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables():
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))


def make_client() -> httpx.AsyncClient:
    """A browser-like client: keeps cookies and echoes the CSRF cookie."""
    client: httpx.AsyncClient

    async def add_csrf(request: httpx.Request) -> None:
        csrf = client.cookies.get("envo_csrf")
        if csrf and request.method not in ("GET", "HEAD", "OPTIONS"):
            request.headers.setdefault("X-CSRF-Token", csrf)

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        event_hooks={"request": [add_csrf]},
    )
    return client


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


async def signup(
    email: str | None = None, password: str = "correct-horse-battery"
) -> tuple[httpx.AsyncClient, dict]:
    c = make_client()
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = await c.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return c, r.json()


@pytest.fixture
async def new_user():
    clients: list[httpx.AsyncClient] = []

    async def factory(email: str | None = None):
        c, user = await signup(email)
        clients.append(c)
        return c, user

    yield factory
    for c in clients:
        await c.aclose()


async def add_member(org_id: str, user_id: str, role: Role) -> str:
    """Insert a membership directly (invitations arrive in phase 4)."""
    async with SessionLocal() as session:
        m = Membership(organization_id=uuid.UUID(org_id), user_id=uuid.UUID(user_id), role=role)
        session.add(m)
        await session.commit()
        return str(m.id)
