from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.db import SessionLocal, utcnow
from app.modules.audit_logs.models import AuditEvent
from app.modules.authorization.policy import Role
from app.modules.service_tokens.models import ServiceToken
from app.modules.versions.models import EnvironmentRevision
from tests.conftest import add_project_member, create_group, create_project, make_client


async def setup(owner):
    group = await create_group(owner, "Acme")
    project = await create_project(owner, "API", group["id"])
    envs = {
        e["slug"]: e
        for e in (await owner.get(f"/api/projects/{project['id']}/environments")).json()
    }
    for slug in ("development", "production"):
        r = await owner.put(
            f"/api/projects/{project['id']}/environments/{envs[slug]['id']}/variables/DB_URL",
            json={"value": f"{slug}-db"},
        )
        assert r.status_code == 200
    return project, envs


async def create_token(owner, project, env_ids, can_write=False, days=30) -> dict:
    r = await owner.post(
        f"/api/projects/{project['id']}/service-tokens",
        json={
            "name": "ci",
            "environment_ids": env_ids,
            "can_write": can_write,
            "expires_in_days": days,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_read_only_token_scope(new_user):
    owner, _ = await new_user()
    project, envs = await setup(owner)
    created = await create_token(owner, project, [envs["development"]["id"]])
    token = created["token"]
    assert token.startswith("envo_st_")
    info = created["service_token"]
    assert info["hint"] == token[8:14] and [e["slug"] for e in info["environments"]] == [
        "development"
    ]
    base = f"/api/projects/{project['id']}/environments"
    dev = f"{base}/{envs['development']['id']}"
    prod = f"{base}/{envs['production']['id']}"

    async with make_client() as ci:
        listed = (await ci.get(base, headers=bearer(token))).json()
        assert [e["slug"] for e in listed] == ["development"]
        r = await ci.get(f"{dev}/export?format=json", headers=bearer(token))
        assert r.json() == {"DB_URL": "development-db"}
        assert (
            await ci.post(f"{dev}/variables/reveal", json={}, headers=bearer(token))
        ).status_code == 200
        # Other environments do not exist for the token.
        assert (await ci.get(f"{prod}/export", headers=bearer(token))).status_code == 404
        # Read-only: writes are refused.
        r = await ci.put(f"{dev}/variables/NEW", json={"value": "x"}, headers=bearer(token))
        assert r.status_code == 403
        r = await ci.post(f"{dev}/import", json={"content": "A=1"}, headers=bearer(token))
        assert r.status_code == 403

        me = (await ci.get("/api/service-tokens/self", headers=bearer(token))).json()
        assert me["project_path"] == "acme/api" and me["can_write"] is False


async def test_write_token_and_history(new_user):
    owner, _ = await new_user()
    project, envs = await setup(owner)
    created = await create_token(owner, project, [envs["production"]["id"]], can_write=True)
    prod = f"/api/projects/{project['id']}/environments/{envs['production']['id']}"
    async with make_client() as ci:
        r = await ci.post(
            f"{prod}/import",
            json={"content": "DB_URL=rotated\nNEW=1"},
            headers=bearer(created["token"]),
        )
        assert r.status_code == 200 and r.json()["revision"] == 2
    async with SessionLocal() as s:
        rev = await s.scalar(select(EnvironmentRevision).where(EnvironmentRevision.revision == 2))
        assert rev.source.value == "token" and rev.actor_user_id is None
        assert str(rev.actor_token_id) == created["service_token"]["id"]
        event = await s.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == "variables.updated")
            .order_by(AuditEvent.created_at.desc())
        )
        assert str(event.actor_token_id) == created["service_token"]["id"]


async def test_token_cannot_use_anything_else(new_user):
    owner, _ = await new_user()
    project, envs = await setup(owner)
    other = await create_project(owner, "Other")
    token = (await create_token(owner, project, [envs["development"]["id"]], can_write=True))[
        "token"
    ]
    async with make_client() as ci:
        for method, path in [
            ("GET", "/api/auth/me"),
            ("GET", "/api/tree"),
            ("GET", f"/api/projects/{project['id']}"),
            ("GET", f"/api/projects/{project['id']}/members"),
            ("GET", f"/api/projects/{project['id']}/service-tokens"),
            ("POST", f"/api/projects/{project['id']}/environments"),
            ("POST", "/api/projects"),
        ]:
            r = await ci.request(
                method, path, json={} if method == "POST" else None, headers=bearer(token)
            )
            assert r.status_code == 403 and r.json()["detail"] == "service_token_not_allowed", (
                method,
                path,
                r.status_code,
            )
        # Another project is invisible.
        r = await ci.get(f"/api/projects/{other['id']}/environments", headers=bearer(token))
        assert r.status_code == 404


@pytest.mark.parametrize("state", ["revoked", "expired", "unknown"])
async def test_invalid_tokens_are_rejected(new_user, state):
    owner, _ = await new_user()
    project, envs = await setup(owner)
    created = await create_token(owner, project, [envs["development"]["id"]])
    token = created["token"]
    if state == "revoked":
        r = await owner.delete(
            f"/api/projects/{project['id']}/service-tokens/{created['service_token']['id']}"
        )
        assert r.status_code == 204
    elif state == "expired":
        async with SessionLocal() as s:
            await s.execute(update(ServiceToken).values(expires_at=utcnow() - timedelta(seconds=1)))
            await s.commit()
    else:
        token = "envo_st_" + "x" * 43
    async with make_client() as ci:
        r = await ci.get(f"/api/projects/{project['id']}/environments", headers=bearer(token))
        assert r.status_code == 401 and r.json()["detail"] == "invalid_token"


async def test_token_management(new_user):
    owner, _ = await new_user()
    dev, dev_user = await new_user()
    project, envs = await setup(owner)
    other = await create_project(owner, "Other")
    other_env = (await owner.get(f"/api/projects/{other['id']}/environments")).json()[0]
    await add_project_member(project["id"], dev_user["id"], Role.DEVELOPER)
    url = f"/api/projects/{project['id']}/service-tokens"

    # Environments must belong to the project.
    r = await owner.post(url, json={"name": "x", "environment_ids": [other_env["id"]]})
    assert r.status_code == 400 and r.json()["detail"] == "invalid_environment"
    # Developers cannot manage tokens.
    assert (await dev.get(url)).status_code == 403
    r = await dev.post(url, json={"name": "x", "environment_ids": [envs["development"]["id"]]})
    assert r.status_code == 403

    created = await create_token(owner, project, [envs["development"]["id"]], days=None)
    assert created["service_token"]["expires_at"] is None
    listed = (await owner.get(url)).json()
    assert [t["id"] for t in listed] == [created["service_token"]["id"]]
    assert "token" not in listed[0] and listed[0]["last_used_at"] is None
    assert listed[0]["created_by"] is not None

    async with make_client() as ci:
        await ci.get(
            f"/api/projects/{project['id']}/environments", headers=bearer(created["token"])
        )
    assert (await owner.get(url)).json()[0]["last_used_at"] is not None

    async with SessionLocal() as s:
        stored = await s.scalar(select(ServiceToken))
        assert created["token"] not in stored.token_hash
