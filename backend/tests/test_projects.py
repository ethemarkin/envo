from app.modules.authorization.policy import Role
from tests.conftest import add_group_member, add_project_member, create_group, create_project


async def test_project_gets_default_environments(new_user):
    c, _ = await new_user()
    project = await create_project(c, "Web API", description="Main")
    assert project["slug"] == "web-api"
    envs = (await c.get(f"/api/projects/{project['id']}/environments")).json()
    assert [(e["slug"], e["protected"]) for e in envs] == [
        ("development", False),
        ("staging", False),
        ("production", True),
    ]
    assert all(e["revision"] == 0 for e in envs)


async def test_project_update_and_delete(new_user):
    c, _ = await new_user()
    project = await create_project(c, "Web API", description="Main")
    url = f"/api/projects/{project['id']}"
    r = await c.patch(url, json={"name": "Renamed", "description": None})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed" and r.json()["description"] is None
    assert r.json()["slug"] == "web-api"

    await create_project(c, "Other", slug="other")
    assert (await c.patch(url, json={"slug": "other"})).status_code == 409

    assert (await c.delete(url)).status_code == 204
    assert (await c.get(url)).status_code == 404


async def test_invalid_slug_is_rejected(new_user):
    c, _ = await new_user()
    r = await c.post("/api/projects", json={"name": "X", "slug": "Bad Slug"})
    assert r.status_code == 422


async def test_environment_crud(new_user):
    c, _ = await new_user()
    project = await create_project(c)
    base = f"/api/projects/{project['id']}/environments"

    r = await c.post(base, json={"name": "QA Sandbox"})
    assert r.status_code == 201
    env = r.json()
    assert env["slug"] == "qa-sandbox" and env["protected"] is False

    assert (await c.post(base, json={"name": "Staging"})).status_code == 409

    r = await c.patch(f"{base}/{env['id']}", json={"protected": True, "name": "QA"})
    assert r.status_code == 200
    assert r.json()["protected"] is True and r.json()["name"] == "QA"

    assert (await c.delete(f"{base}/{env['id']}")).status_code == 204
    assert len((await c.get(base)).json()) == 3


async def test_developer_cannot_manage_environments(new_user):
    owner, _ = await new_user()
    dev, dev_user = await new_user()
    group = await create_group(owner)
    project = await create_project(owner, "API", group["id"])
    await add_group_member(group["id"], dev_user["id"], Role.DEVELOPER)
    base = f"/api/projects/{project['id']}/environments"
    envs = (await dev.get(base)).json()
    assert len(envs) == 3
    assert (await dev.post(base, json={"name": "Mine"})).status_code == 403
    prod = next(e for e in envs if e["slug"] == "production")
    assert (await dev.patch(f"{base}/{prod['id']}", json={"protected": False})).status_code == 403


async def test_project_admin_can_manage_but_not_delete(new_user):
    owner, _ = await new_user()
    admin, admin_user = await new_user()
    project = await create_project(owner)
    await add_project_member(project["id"], admin_user["id"], Role.ADMIN)
    url = f"/api/projects/{project['id']}"
    assert (await admin.patch(url, json={"name": "Renamed"})).status_code == 200
    assert (await admin.post(f"{url}/environments", json={"name": "QA"})).status_code == 201
    assert (await admin.delete(url)).status_code == 403


async def test_environment_of_other_project_is_not_reachable(new_user):
    c, _ = await new_user()
    project = await create_project(c, "One")
    other = await create_project(c, "Other")
    env = (await c.get(f"/api/projects/{other['id']}/environments")).json()[0]
    r = await c.patch(
        f"/api/projects/{project['id']}/environments/{env['id']}", json={"name": "Hijack"}
    )
    assert r.status_code == 404
