from app.modules.authorization.policy import Role
from tests.conftest import add_project_member, create_project, make_client


async def setup(c, slug="development"):
    project = await create_project(c, "API")
    envs = (await c.get(f"/api/projects/{project['id']}/environments")).json()
    env = next(e for e in envs if e["slug"] == slug)
    return project, f"/api/projects/{project['id']}/environments/{env['id']}"


async def write(c, base, upserts=(), deletes=()):
    r = await c.patch(
        f"{base}/variables", json={"upserts": list(upserts), "deletes": list(deletes)}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def export(c, base) -> dict:
    return (await c.get(f"{base}/export?format=json")).json()


async def test_history_lists_change_sets_without_values(new_user):
    c, user = await new_user()
    _, base = await setup(c)
    await write(
        c, base, [{"key": "A", "value": "value-one-x"}, {"key": "B", "value": "value-two-x"}]
    )
    await write(c, base, [{"key": "A", "value": "value-uno-x", "visibility": "visible"}], ["B"])

    page = (await c.get(f"{base}/revisions")).json()
    assert page["current_revision"] == 2 and page["next_before"] is None
    assert [r["revision"] for r in page["revisions"]] == [2, 1]
    latest = page["revisions"][0]
    assert latest["source"] == "web" and latest["actor"]["type"] == "user"
    assert [(ch["key"], ch["action"], ch["visibility"]) for ch in latest["changes"]] == [
        ("A", "update", "visible"),
        ("B", "delete", None),
    ]
    assert "value-" not in str(page)


async def test_history_pagination(new_user):
    c, _ = await new_user()
    _, base = await setup(c)
    for i in range(5):
        await write(c, base, [{"key": "A", "value": str(i)}])
    first = (await c.get(f"{base}/revisions?limit=2")).json()
    assert [r["revision"] for r in first["revisions"]] == [5, 4] and first["next_before"] == 4
    second = (await c.get(f"{base}/revisions?limit=2&before=4")).json()
    assert [r["revision"] for r in second["revisions"]] == [3, 2]
    last = (await c.get(f"{base}/revisions?limit=2&before=2")).json()
    assert [r["revision"] for r in last["revisions"]] == [1] and last["next_before"] is None


async def test_rollback_restores_values_and_visibility_as_new_revision(new_user):
    c, _ = await new_user()
    _, base = await setup(c)
    await write(
        c,
        base,
        [
            {"key": "DB", "value": "old-db"},
            {"key": "LOG", "value": "info", "visibility": "visible"},
        ],
    )  # rev 1
    await write(
        c, base, [{"key": "DB", "value": "new-db"}, {"key": "NEW", "value": "x"}], ["LOG"]
    )  # 2
    await write(c, base, [{"key": "DB", "visibility": "visible"}])  # 3

    r = await c.post(f"{base}/revisions/1/rollback")
    assert r.status_code == 200, r.text
    assert r.json() == {"revision": 4, "created": ["LOG"], "updated": ["DB"], "deleted": ["NEW"]}
    assert await export(c, base) == {"DB": "old-db", "LOG": "info"}
    listing = {v["key"]: v for v in (await c.get(f"{base}/variables")).json()["variables"]}
    assert listing["DB"]["visibility"] == "secret" and listing["LOG"]["visibility"] == "visible"

    latest = (await c.get(f"{base}/revisions?limit=1")).json()["revisions"][0]
    assert latest["source"] == "rollback" and latest["message"] == "rollback to 1"

    # History is kept: rolling forward again works.
    await c.post(f"{base}/revisions/3/rollback")
    assert await export(c, base) == {"DB": "new-db", "NEW": "x"}


async def test_rollback_to_zero_empties_and_current_is_noop(new_user):
    c, _ = await new_user()
    _, base = await setup(c)
    await write(c, base, [{"key": "A", "value": "1"}])
    noop = (await c.post(f"{base}/revisions/1/rollback")).json()
    assert noop == {"revision": 1, "created": [], "updated": [], "deleted": []}
    r = (await c.post(f"{base}/revisions/0/rollback")).json()
    assert r["deleted"] == ["A"] and await export(c, base) == {}
    assert (await c.post(f"{base}/revisions/99/rollback")).status_code == 404


async def test_rollback_detects_concurrent_changes(new_user):
    c, _ = await new_user()
    _, base = await setup(c)
    await write(c, base, [{"key": "A", "value": "1"}])
    await write(c, base, [{"key": "A", "value": "2"}])
    r = await c.post(f"{base}/revisions/1/rollback", headers={"If-Match": '"1"'})
    assert r.status_code == 409 and r.json()["detail"] == "revision_conflict"
    assert (await export(c, base)) == {"A": "2"}


async def test_rollback_needs_write_permission(new_user):
    owner, _ = await new_user()
    viewer, viewer_user = await new_user()
    dev, dev_user = await new_user()
    project, prod = await setup(owner, "production")
    await add_project_member(project["id"], viewer_user["id"], Role.VIEWER)
    await add_project_member(project["id"], dev_user["id"], Role.DEVELOPER)
    await write(owner, prod, [{"key": "A", "value": "1"}])
    await write(owner, prod, [{"key": "A", "value": "2"}])

    # Everyone with a role may read the history (no values in it).
    assert (await viewer.get(f"{prod}/revisions")).status_code == 200
    assert (await viewer.post(f"{prod}/revisions/1/rollback")).status_code == 403
    # Production is protected: developers cannot write there.
    assert (await dev.post(f"{prod}/revisions/1/rollback")).status_code == 403
    assert (await owner.post(f"{prod}/revisions/1/rollback")).status_code == 200


async def test_service_token_rollback_is_attributed_to_the_token(new_user):
    owner, _ = await new_user()
    project, base = await setup(owner)
    await write(owner, base, [{"key": "A", "value": "1"}])
    await write(owner, base, [{"key": "A", "value": "2"}])
    env_id = base.rsplit("/", 1)[1]
    token = (
        await owner.post(
            f"/api/projects/{project['id']}/service-tokens",
            json={"name": "deployer", "environment_ids": [env_id], "can_write": True},
        )
    ).json()["token"]
    async with make_client() as ci:
        r = await ci.post(
            f"{base}/revisions/1/rollback", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
    latest = (await owner.get(f"{base}/revisions?limit=1")).json()["revisions"][0]
    assert latest["actor"] == {"type": "token", "id": latest["actor"]["id"], "label": "deployer"}
