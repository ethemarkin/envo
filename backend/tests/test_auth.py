from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal, utcnow
from app.core.security import hash_token
from app.modules.auth.models import RefreshToken
from tests.conftest import make_client


async def test_signup_sets_http_only_cookies_and_returns_user(client):
    r = await client.post(
        "/api/auth/signup", json={"email": "  Ada@Example.com ", "password": "long-enough-pw"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "ada@example.com"
    assert body["has_password"] is True
    assert body["providers"] == []

    set_cookie = r.headers.get_list("set-cookie")
    access = next(c for c in set_cookie if c.startswith("envo_access="))
    refresh = next(c for c in set_cookie if c.startswith("envo_refresh="))
    csrf = next(c for c in set_cookie if c.startswith("envo_csrf="))
    assert "HttpOnly" in access and "Path=/api" in access and "SameSite=lax" in access
    assert "HttpOnly" in refresh and "Path=/api/auth" in refresh
    assert "HttpOnly" not in csrf

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"


async def test_duplicate_email_is_rejected(client, new_user):
    await new_user("dup@example.com")
    r = await client.post(
        "/api/auth/signup", json={"email": "DUP@example.com", "password": "long-enough-pw"}
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "email_taken"


async def test_short_password_is_rejected(client):
    r = await client.post("/api/auth/signup", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


async def test_login(new_user):
    c, _ = await new_user("login@example.com")
    await c.aclose()
    async with make_client() as fresh:
        bad = await fresh.post(
            "/api/auth/login", json={"email": "login@example.com", "password": "wrong-password"}
        )
        assert bad.status_code == 401
        assert bad.json()["detail"] == "invalid_credentials"

        unknown = await fresh.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"}
        )
        assert unknown.status_code == 401

        ok = await fresh.post(
            "/api/auth/login",
            json={"email": "LOGIN@example.com", "password": "correct-horse-battery"},
        )
        assert ok.status_code == 200
        assert (await fresh.get("/api/auth/me")).status_code == 200


async def test_unauthenticated_request_is_rejected(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401


async def test_cookie_request_without_csrf_header_is_rejected(new_user):
    c, _ = await new_user()
    r = await c.post("/api/orgs", json={"name": "Acme"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_failed"


async def test_bearer_token_needs_no_csrf(new_user):
    c, _ = await new_user()
    access = c.cookies.get("envo_access")
    async with make_client() as other:
        r = await other.post(
            "/api/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {access}"}
        )
        assert r.status_code == 201


async def test_refresh_rotates_token(new_user):
    c, _ = await new_user()
    old = c.cookies.get("envo_refresh")
    r = await c.post("/api/auth/refresh")
    assert r.status_code == 204
    new = c.cookies.get("envo_refresh")
    assert new and new != old
    assert (await c.get("/api/auth/me")).status_code == 200


async def test_reused_refresh_token_revokes_the_family(new_user):
    c, _ = await new_user()
    old = c.cookies.get("envo_refresh")
    assert (await c.post("/api/auth/refresh")).status_code == 204
    current = c.cookies.get("envo_refresh")

    # Move the rotation outside the grace window, then replay the old token.
    async with SessionLocal() as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(old))
            .values(rotated_at=utcnow() - timedelta(minutes=5))
        )
        await s.commit()

    csrf = c.cookies.get("envo_csrf")
    async with make_client() as attacker:
        attacker.cookies.set("envo_refresh", old, path="/api/auth")
        attacker.cookies.set("envo_csrf", csrf)
        r = await attacker.post("/api/auth/refresh")
        assert r.status_code == 401
        assert r.json()["detail"] == "refresh_token_reused"

    # The legitimate session's newer token is revoked as well.
    async with SessionLocal() as s:
        row = await s.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(current))
        )
        assert row is not None and row.revoked_at is not None


async def test_concurrent_refresh_within_grace_is_allowed(new_user):
    c, _ = await new_user()
    old = c.cookies.get("envo_refresh")
    csrf = c.cookies.get("envo_csrf")
    assert (await c.post("/api/auth/refresh")).status_code == 204
    async with make_client() as second_tab:
        second_tab.cookies.set("envo_refresh", old, path="/api/auth")
        second_tab.cookies.set("envo_csrf", csrf)
        assert (await second_tab.post("/api/auth/refresh")).status_code == 204


async def test_logout_revokes_refresh_token(new_user):
    c, _ = await new_user()
    refresh = c.cookies.get("envo_refresh")
    csrf = c.cookies.get("envo_csrf")
    assert (await c.post("/api/auth/logout")).status_code == 204
    async with make_client() as replay:
        replay.cookies.set("envo_refresh", refresh, path="/api/auth")
        replay.cookies.set("envo_csrf", csrf)
        assert (await replay.post("/api/auth/refresh")).status_code == 401


async def test_refresh_without_session_is_401(client):
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 401


async def test_refresh_requires_csrf(new_user):
    c, _ = await new_user()
    r = await c.post("/api/auth/refresh", headers={"X-CSRF-Token": "nope"})
    assert r.status_code == 403


async def test_google_disabled_by_default(client):
    assert (await client.get("/api/auth/config")).json() == {"google_enabled": False}
    assert (await client.get("/api/auth/google/start")).status_code == 404
