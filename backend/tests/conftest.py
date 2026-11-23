"""Test setup: a real PostgreSQL database (envo_test) migrated with Alembic.

Requires a PostgreSQL server (e.g. the docker compose `db` service published
on localhost:5432). The test database is created on first use. Override the
URL with ENVO_TEST_DATABASE_URL if the database lives elsewhere.
"""

import asyncio
import os
import uuid
from datetime import timedelta
from pathlib import Path

os.environ["ENVO_DATABASE_URL"] = os.environ.get(
    "ENVO_TEST_DATABASE_URL", "postgresql+asyncpg://envo:envo@localhost:5432/envo_test"
)
os.environ["ENVO_SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["ENVO_COOKIE_SECURE"] = "false"
# Fixed test-only master key (32 bytes, base64).
os.environ["ENVO_MASTER_KEY"] = "dGVzdC1tYXN0ZXIta2V5LTMyLWJ5dGVzLWxvbmchISE="
os.environ["ENVO_MASTER_KEY_ID"] = "test1"
os.environ["ENVO_RETIRED_MASTER_KEYS"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine, utcnow  # noqa: E402
from app.core.security import hash_token, new_opaque_token  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.models import User  # noqa: E402
from app.modules.authorization.policy import Role  # noqa: E402
from app.modules.groups.invitation_models import Invitation  # noqa: E402
from app.modules.groups.models import GroupMember  # noqa: E402
from app.modules.projects.models import ProjectMember  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
TABLES = [
    "service_token_environments",
    "service_tokens",
    "invitations",
    "cli_login_requests",
    "audit_events",
    "variable_revisions",
    "environment_revisions",
    "variables",
    "environments",
    "project_folders",
    "project_members",
    "projects",
    "group_members",
    "groups",
    "refresh_tokens",
    "users",
]


async def ensure_test_database(url: str) -> None:
    """Create the test database if the server does not have it yet."""
    import asyncpg
    from sqlalchemy.engine import make_url

    target = make_url(url)
    conn = await asyncpg.connect(
        host=target.host,
        port=target.port or 5432,
        user=target.username,
        password=target.password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target.database
        )
        if not exists:
            # Identifier from our own config, not user input.
            await conn.execute(f'CREATE DATABASE "{target.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def database():
    await ensure_test_database(os.environ["ENVO_DATABASE_URL"])
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


ADMIN_EMAIL = "instance-admin@example.com"


@pytest.fixture(autouse=True)
async def clean_tables():
    # A pre-existing administrator, so users created by tests are regular
    # users (the first account of an instance becomes its administrator).
    async with SessionLocal() as session:
        session.add(User(email=ADMIN_EMAIL, is_admin=True))
        await session.commit()
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
        await conn.execute(text("UPDATE instance_settings SET allow_root_creation = true"))


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


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
    """Captures e-mail instead of sending it. Set `outbox.smtp = False` to
    simulate an instance without SMTP."""
    from app.core.mail import Mail

    class Outbox(list[Mail]):
        smtp = True

    box = Outbox()

    async def fake_deliver(mail: Mail) -> bool:
        if not box.smtp:
            return False
        box.append(mail)
        return True

    monkeypatch.setattr("app.modules.authorization.members.deliver", fake_deliver)
    monkeypatch.setattr("app.modules.admin.router.deliver", fake_deliver)
    return box


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


async def invite_token(email: str) -> str:
    """A pending sign-up invitation for `email`, as an administrator would
    send it (sign-up requires one). Returns the link token."""
    token = new_opaque_token()
    async with SessionLocal() as session:
        session.add(
            Invitation(
                email=email.strip().lower(),
                token_hash=hash_token(token),
                expires_at=utcnow() + timedelta(days=1),
            )
        )
        await session.commit()
    return token


async def signup(
    email: str | None = None, password: str = "correct-horse-battery"
) -> tuple[httpx.AsyncClient, dict]:
    c = make_client()
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = await c.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "invite_token": await invite_token(email)},
    )
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


async def add_group_member(group_id: str, user_id: str, role: Role) -> str:
    async with SessionLocal() as session:
        m = GroupMember(group_id=uuid.UUID(group_id), user_id=uuid.UUID(user_id), role=role)
        session.add(m)
        await session.commit()
        return str(m.id)


async def add_project_member(project_id: str, user_id: str, role: Role) -> str:
    async with SessionLocal() as session:
        m = ProjectMember(project_id=uuid.UUID(project_id), user_id=uuid.UUID(user_id), role=role)
        session.add(m)
        await session.commit()
        return str(m.id)


async def create_group(c, name: str = "Acme", parent_id: str | None = None, **extra) -> dict:
    r = await c.post("/api/groups", json={"name": name, "parent_id": parent_id, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def create_project(c, name: str = "API", group_id: str | None = None, **extra) -> dict:
    r = await c.post("/api/projects", json={"name": name, "group_id": group_id, **extra})
    assert r.status_code == 201, r.text
    return r.json()
