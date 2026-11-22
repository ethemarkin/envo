import uuid

import pytest
from sqlalchemy import select

from app.core.crypto import get_key_provider
from app.core.db import SessionLocal
from app.modules.audit_logs.models import AuditEvent
from app.modules.authorization.policy import Role
from app.modules.environments.models import Environment
from app.modules.variables.models import Variable
from app.modules.variables.rotate import rewrap_deks
from app.modules.versions.models import EnvironmentRevision, VariableRevision
from tests.conftest import add_group_member, create_group, create_project


class Env:
    """Paths for one environment of a fresh group/project."""

    def __init__(self, group: dict, project: dict, env: dict) -> None:
        self.group, self.project, self.env = group, project, env
        self.base = f"/api/projects/{project['id']}/environments/{env['id']}"

    @property
    def id(self) -> uuid.UUID:
        return uuid.UUID(self.env["id"])


async def make_env(c, slug: str = "development") -> Env:
    group = await create_group(c, "Acme")
    project = await create_project(c, "API", group["id"])
    envs = (await c.get(f"/api/projects/{project['id']}/environments")).json()
    return Env(group, project, next(e for e in envs if e["slug"] == slug))


async def write(c, e: Env, upserts=(), deletes=(), **headers):
    return await c.patch(
        f"{e.base}/variables",
        json={"upserts": list(upserts), "deletes": list(deletes)},
        headers=headers,
    )


async def listing(c, e: Env) -> dict:
    r = await c.get(f"{e.base}/variables")
    assert r.status_code == 200, r.text
    return r.json()


async def test_values_are_encrypted_and_secrets_masked(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    r = await write(
        c,
        e,
        [
            {"key": "DATABASE_URL", "value": "postgres://user:hunter2@db/app"},
            {"key": "LOG_LEVEL", "value": "debug", "visibility": "visible"},
        ],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "revision": 1,
        "created": ["DATABASE_URL", "LOG_LEVEL"],
        "updated": [],
        "deleted": [],
    }

    body = await listing(c, e)
    assert body["revision"] == 1
    assert [(v["key"], v["visibility"], v["value"]) for v in body["variables"]] == [
        ("DATABASE_URL", "secret", None),
        ("LOG_LEVEL", "visible", "debug"),
    ]

    async with SessionLocal() as s:
        rows = (await s.scalars(select(Variable))).all()
        assert all(b"hunter2" not in v.ciphertext and b"debug" not in v.ciphertext for v in rows)
        env = await s.get(Environment, e.id)
        assert env.wrapped_dek is not None and env.kek_id == "test1"


async def test_reveal_and_export(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    await write(
        c,
        e,
        [
            {"key": "B_SECRET", "value": "multi\nline 'q' \"dq\""},
            {"key": "A_VISIBLE", "value": "x", "visibility": "visible"},
        ],
    )
    r = await c.post(f"{e.base}/variables/reveal", json={})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {"values": {"B_SECRET": "multi\nline 'q' \"dq\""}}

    r = await c.post(f"{e.base}/variables/reveal", json={"keys": ["A_VISIBLE"]})
    assert r.json() == {"values": {"A_VISIBLE": "x"}}

    r = await c.get(f"{e.base}/export?format=json")
    assert r.json() == {"A_VISIBLE": "x", "B_SECRET": "multi\nline 'q' \"dq\""}

    r = await c.get(f"{e.base}/export")
    assert r.headers["content-disposition"] == 'attachment; filename="api.development.env"'
    # The export is importable again and changes nothing.
    again = await c.post(f"{e.base}/import", json={"content": r.text})
    assert again.status_code == 200
    assert {i["status"] for i in again.json()["items"]} == {"unchanged"}
    assert again.json()["revision"] == 1


async def test_updates_record_history(new_user):
    c, user = await new_user()
    e = await make_env(c)
    await write(c, e, [{"key": "A", "value": "1"}, {"key": "B", "value": "1"}])
    r = await write(
        c,
        e,
        [
            {"key": "A", "value": "2"},
            {"key": "B", "visibility": "visible"},
            {"key": "C", "value": "new"},
        ],
    )
    assert r.json() == {"revision": 2, "created": ["C"], "updated": ["A", "B"], "deleted": []}
    r = await write(c, e, deletes=["C"])
    assert r.json()["deleted"] == ["C"] and r.json()["revision"] == 3

    # Writing identical values is a no-op: no new revision.
    r = await write(c, e, [{"key": "A", "value": "2"}])
    assert r.json() == {"revision": 3, "created": [], "updated": [], "deleted": []}

    async with SessionLocal() as s:
        revs = (
            await s.scalars(
                select(EnvironmentRevision)
                .where(EnvironmentRevision.environment_id == e.id)
                .order_by(EnvironmentRevision.revision)
            )
        ).all()
        assert [(r.revision, r.source.value, str(r.actor_user_id)) for r in revs] == [
            (1, "web", user["id"]),
            (2, "web", user["id"]),
            (3, "web", user["id"]),
        ]
        changes = (
            await s.scalars(
                select(VariableRevision)
                .where(VariableRevision.environment_id == e.id)
                .order_by(VariableRevision.revision, VariableRevision.key)
            )
        ).all()
        assert [(v.revision, v.key, v.action.value) for v in changes] == [
            (1, "A", "create"),
            (1, "B", "create"),
            (2, "A", "update"),
            (2, "B", "update"),
            (2, "C", "create"),
            (3, "C", "delete"),
        ]
        assert changes[-1].ciphertext is None


async def test_if_match_detects_concurrent_edits(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    await write(c, e, [{"key": "A", "value": "1"}])
    etag = (await c.get(f"{e.base}/variables")).headers["etag"]
    assert etag == '"1"'
    await write(c, e, [{"key": "A", "value": "2"}])  # someone else
    r = await write(c, e, [{"key": "A", "value": "3"}], **{"If-Match": etag})
    assert r.status_code == 409 and r.json()["detail"] == "revision_conflict"
    r = await write(c, e, [{"key": "A", "value": "3"}], **{"If-Match": '"2"'})
    assert r.status_code == 200 and r.json()["revision"] == 3


@pytest.mark.parametrize(
    ("upserts", "deletes", "status", "code"),
    [
        ([{"key": "1BAD", "value": "x"}], [], 422, "invalid_key"),
        ([{"key": "A", "value": "x"}, {"key": "A", "value": "y"}], [], 422, "duplicate_key"),
        ([{"key": "NEW"}], [], 422, "value_required"),
        ([], ["MISSING"], 404, "variable_not_found"),
    ],
)
async def test_invalid_writes_change_nothing(new_user, upserts, deletes, status, code):
    c, _ = await new_user()
    e = await make_env(c)
    await write(c, e, [{"key": "KEEP", "value": "1"}])
    r = await write(c, e, [*upserts, {"key": "OTHER", "value": "x"}], deletes)
    assert r.status_code == status and r.json()["detail"] == code
    body = await listing(c, e)
    assert body["revision"] == 1 and [v["key"] for v in body["variables"]] == ["KEEP"]


async def test_import_merges_and_keeps_existing_visibility(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    await write(
        c,
        e,
        [
            {"key": "UNTOUCHED", "value": "stays"},
            {"key": "SHOWN", "value": "old", "visibility": "visible"},
            {"key": "SAME", "value": "same"},
        ],
    )
    content = "SHOWN=new\nSAME=same\nNEW_SECRET=s\nNEW_VISIBLE=v\n"
    payload = {
        "content": content,
        "visibility": {"NEW_VISIBLE": "visible", "SHOWN": "secret"},
    }

    preview = await c.post(f"{e.base}/import", json={**payload, "dry_run": True})
    assert preview.status_code == 200
    assert preview.json() == {
        "revision": 1,
        "dry_run": True,
        "items": [
            {"key": "SHOWN", "status": "changed", "visibility": "visible"},
            {"key": "SAME", "status": "unchanged", "visibility": "secret"},
            {"key": "NEW_SECRET", "status": "new", "visibility": "secret"},
            {"key": "NEW_VISIBLE", "status": "new", "visibility": "visible"},
        ],
    }
    assert (await listing(c, e))["revision"] == 1  # dry run wrote nothing

    r = await c.post(f"{e.base}/import", json=payload)
    assert r.json()["revision"] == 2
    vars_ = {v["key"]: v for v in (await listing(c, e))["variables"]}
    assert set(vars_) == {"UNTOUCHED", "SHOWN", "SAME", "NEW_SECRET", "NEW_VISIBLE"}
    assert vars_["SHOWN"]["visibility"] == "visible" and vars_["SHOWN"]["value"] == "new"
    assert vars_["NEW_SECRET"]["visibility"] == "secret"
    assert vars_["NEW_VISIBLE"]["value"] == "v"


async def test_invalid_import_is_rejected_with_line_numbers(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    r = await c.post(f"{e.base}/import", json={"content": "GOOD=1\nBAD KEY=2\nGOOD=3"})
    assert r.status_code == 422
    assert r.json()["detail"] == "invalid_dotenv"
    assert [(x["line"], x["code"]) for x in r.json()["errors"]] == [
        (2, "invalid_key"),
        (3, "duplicate_key"),
    ]
    assert (await listing(c, e))["variables"] == []


async def test_single_set_and_delete(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    r = await c.put(f"{e.base}/variables/API_KEY", json={"value": "abc"})
    assert r.json()["created"] == ["API_KEY"]
    r = await c.put(f"{e.base}/variables/API_KEY", json={"value": "def"})
    assert r.json()["updated"] == ["API_KEY"]
    r = await c.delete(f"{e.base}/variables/API_KEY")
    assert r.json()["deleted"] == ["API_KEY"]
    assert (await c.delete(f"{e.base}/variables/API_KEY")).status_code == 404


async def test_bearer_writes_are_recorded_as_cli(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    token = c.cookies.get("envo_access")
    r = await c.put(
        f"{e.base}/variables/FROM_CLI",
        json={"value": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    async with SessionLocal() as s:
        rev = await s.scalar(
            select(EnvironmentRevision).where(EnvironmentRevision.environment_id == e.id)
        )
        assert rev.source.value == "cli"


# --- Role matrix -------------------------------------------------------------

# (role, protected) -> (can read secrets, can write)
MATRIX = {
    (Role.OWNER, False): (True, True),
    (Role.ADMIN, False): (True, True),
    (Role.DEVELOPER, False): (True, True),
    (Role.VIEWER, False): (False, False),
    (Role.OWNER, True): (True, True),
    (Role.ADMIN, True): (True, True),
    (Role.DEVELOPER, True): (False, False),
    (Role.VIEWER, True): (False, False),
}


@pytest.mark.parametrize(("role", "protected"), list(MATRIX))
async def test_role_matrix(new_user, role, protected):
    owner, _ = await new_user()
    e = await make_env(owner, "production" if protected else "development")
    await write(
        owner,
        e,
        [{"key": "SECRET", "value": "s"}, {"key": "PUBLIC", "value": "p", "visibility": "visible"}],
    )
    member, member_user = await new_user()
    if role != Role.OWNER:
        await add_group_member(e.group["id"], member_user["id"], role)
    else:
        member = owner
    can_read, can_write = MATRIX[(role, protected)]

    body = await listing(member, e)
    assert body["can_read_secrets"] is can_read and body["can_write"] is can_write
    assert {v["key"]: v["value"] for v in body["variables"]} == {"SECRET": None, "PUBLIC": "p"}

    for path, method, payload in [
        ("/variables/reveal", "POST", {}),
        ("/export", "GET", None),
    ]:
        r = await member.request(method, e.base + path, json=payload)
        assert (r.status_code == 200) is can_read, (path, r.status_code)

    for path, method, payload in [
        ("/variables", "PATCH", {"upserts": [{"key": "X", "value": "1"}]}),
        ("/variables/Y", "PUT", {"value": "1"}),
        ("/import", "POST", {"content": "Z=1"}),
        ("/variables/PUBLIC", "DELETE", None),
    ]:
        r = await member.request(method, e.base + path, json=payload)
        assert (r.status_code == 200) is can_write, (path, r.status_code)
        if not can_write:
            assert r.status_code == 403


async def test_other_tenant_cannot_reach_variables(new_user):
    alice, _ = await new_user()
    mallory, _ = await new_user()
    e = await make_env(alice)
    await write(alice, e, [{"key": "SECRET", "value": "s"}])
    for method, path in [
        ("GET", "/variables"),
        ("POST", "/variables/reveal"),
        ("GET", "/export"),
        ("PATCH", "/variables"),
    ]:
        r = await mallory.request(method, e.base + path, json={} if method != "GET" else None)
        assert r.status_code == 404, (method, path)

    # Also not through mallory's own project with alice's environment id.
    own = await make_env(mallory)
    path = f"/api/projects/{own.project['id']}/environments/{e.env['id']}/variables"
    assert (await mallory.get(path)).status_code == 404


async def test_audit_events_never_contain_values(new_user):
    c, _ = await new_user()
    e = await make_env(c)
    await write(c, e, [{"key": "TOKEN", "value": "very-secret-value"}])
    await c.post(f"{e.base}/variables/reveal", json={})
    await c.get(f"{e.base}/export")
    await c.post(f"{e.base}/import", json={"content": "TOKEN=another-secret-value"})

    async with SessionLocal() as s:
        events = (
            await s.scalars(
                select(AuditEvent)
                .where(AuditEvent.resource_id == e.id)
                .order_by(AuditEvent.created_at)
            )
        ).all()
    assert [ev.action for ev in events] == [
        "variables.updated",
        "variables.revealed",
        "variables.exported",
        "variables.updated",
    ]
    dumped = repr([(ev.details, ev.action) for ev in events])
    assert "secret-value" not in dumped
    assert events[1].details["keys"] == ["TOKEN"]


async def test_environment_delete_removes_key_and_values(new_user):
    c, _ = await new_user()
    e = await make_env(c, "staging")
    await write(c, e, [{"key": "A", "value": "1"}])
    env_url = e.base
    assert (await c.delete(env_url)).status_code == 204
    async with SessionLocal() as s:
        assert await s.get(Environment, e.id) is None
        remaining = await s.scalars(select(Variable).where(Variable.environment_id == e.id))
        assert remaining.all() == []


async def test_master_key_rotation_rewraps_without_touching_values(new_user, monkeypatch):
    import os

    from app.core.crypto import LocalKeyProvider

    c, _ = await new_user()
    e = await make_env(c)
    await write(c, e, [{"key": "A", "value": "before-rotation"}])
    async with SessionLocal() as s:
        before = (await s.scalars(select(Variable))).one().ciphertext

    old = get_key_provider()
    new_key = os.urandom(32)
    old_key = old._keys["test1"]  # type: ignore[attr-defined]
    rotated = LocalKeyProvider("k2", {"k2": new_key, "test1": old_key})
    async with SessionLocal() as s:
        assert await rewrap_deks(s, rotated) == 1
        assert await rewrap_deks(s, rotated) == 0

    monkeypatch.setattr("app.modules.variables.service.get_key_provider", lambda: rotated)
    async with SessionLocal() as s:
        env = await s.get(Environment, e.id)
        assert env.kek_id == "k2"
        assert (await s.scalars(select(Variable))).one().ciphertext == before
    r = await c.get(f"{e.base}/export?format=json")
    assert r.json() == {"A": "before-rotation"}
