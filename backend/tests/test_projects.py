from app.modules.authorization.policy import Role
from tests.conftest import add_member


async def setup_project(c):
    org = (await c.post("/api/orgs", json={"name": "Acme"})).json()
    r = await c.post(
        f"/api/orgs/{org['id']}/projects", json={"name": "Web API", "description": "Main"}
    )
    assert r.status_code == 201, r.text
    return org, r.json()


async def test_project_gets_default_environments(new_user):
    c, _ = await new_user()
    org, project = await setup_project(c)
    assert project["slug"] == "web-api"
    envs = (await c.get(f"/api/orgs/{org['id']}/projects/{project['id']}/environments")).json()
    assert [(e["slug"], e["protected"]) for e in envs] == [
        ("development", False),
        ("staging", False),
        ("production", True),
    ]
    assert all(e["revision"] == 0 for e in envs)


async def test_project_update_and_delete(new_user):
    c, _ = await new_user()
    org, project = await setup_project(c)
    url = f"/api/orgs/{org['id']}/projects/{project['id']}"
    r = await c.patch(url, json={"name": "Renamed", "description": None})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed" and r.json()["description"] is None
    assert r.json()["slug"] == "web-api"

    await c.post(f"/api/orgs/{org['id']}/projects", json={"name": "Other", "slug": "other"})
    assert (await c.patch(url, json={"slug": "other"})).status_code == 409

    assert (await c.delete(url)).status_code == 204
    assert (await c.get(url)).status_code == 404


async def test_invalid_slug_is_rejected(new_user):
    c, _ = await new_user()
    org = (await c.post("/api/orgs", json={"name": "Acme"})).json()
    r = await c.post(f"/api/orgs/{org['id']}/projects", json={"name": "X", "slug": "Bad Slug"})
    assert r.status_code == 422


async def test_environment_crud(new_user):
    c, _ = await new_user()
    org, project = await setup_project(c)
    base = f"/api/orgs/{org['id']}/projects/{project['id']}/environments"

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
    org, project = await setup_project(owner)
    await add_member(org["id"], dev_user["id"], Role.DEVELOPER)
    base = f"/api/orgs/{org['id']}/projects/{project['id']}/environments"
    envs = (await dev.get(base)).json()
    assert len(envs) == 3
    assert (await dev.post(base, json={"name": "Mine"})).status_code == 403
    prod = next(e for e in envs if e["slug"] == "production")
    assert (await dev.patch(f"{base}/{prod['id']}", json={"protected": False})).status_code == 403


async def test_environment_of_other_project_is_not_reachable(new_user):
    c, _ = await new_user()
    org, project = await setup_project(c)
    other = (await c.post(f"/api/orgs/{org['id']}/projects", json={"name": "Other"})).json()
    env = (await c.get(f"/api/orgs/{org['id']}/projects/{other['id']}/environments")).json()[0]
    r = await c.patch(
        f"/api/orgs/{org['id']}/projects/{project['id']}/environments/{env['id']}",
        json={"name": "Hijack"},
    )
    assert r.status_code == 404
