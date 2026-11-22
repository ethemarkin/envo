import pytest

from app.modules.authorization.policy import Role
from tests.conftest import add_member


async def create_org(c, name="Acme Corp", **extra):
    r = await c.post("/api/orgs", json={"name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def test_creator_becomes_owner_and_slug_is_derived(new_user):
    c, _ = await new_user()
    org = await create_org(c, "Çağrı Yazılım Şirketi")
    assert org["role"] == "owner"
    assert org["slug"] == "cagri-yazilim-sirketi"
    members = (await c.get(f"/api/orgs/{org['id']}/members")).json()
    assert [m["role"] for m in members] == ["owner"]


async def test_duplicate_slug_gets_suffix_but_explicit_slug_conflicts(new_user):
    c, _ = await new_user()
    first = await create_org(c, "Acme")
    second = await create_org(c, "Acme")
    assert second["slug"].startswith("acme-") and second["slug"] != first["slug"]
    r = await c.post("/api/orgs", json={"name": "X", "slug": "acme"})
    assert r.status_code == 409


async def test_list_contains_only_own_organizations(new_user):
    alice, _ = await new_user()
    bob, _ = await new_user()
    await create_org(alice, "Alice Org")
    await create_org(bob, "Bob Org")
    names = [o["name"] for o in (await alice.get("/api/orgs")).json()]
    assert names == ["Alice Org"]


async def test_other_tenant_gets_404_everywhere(new_user):
    alice, _ = await new_user()
    mallory, _ = await new_user()
    org = await create_org(alice)
    project = (await alice.post(f"/api/orgs/{org['id']}/projects", json={"name": "API"})).json()
    base = f"/api/orgs/{org['id']}"
    for method, path in [
        ("GET", base),
        ("PATCH", base),
        ("DELETE", base),
        ("GET", f"{base}/members"),
        ("GET", f"{base}/projects"),
        ("GET", f"{base}/projects/{project['id']}"),
        ("GET", f"{base}/projects/{project['id']}/environments"),
    ]:
        r = await mallory.request(method, path, json={} if method == "PATCH" else None)
        assert r.status_code == 404, (method, path, r.status_code)


async def test_project_of_another_org_is_not_reachable_through_own_org(new_user):
    alice, _ = await new_user()
    mallory, _ = await new_user()
    alice_org = await create_org(alice)
    mallory_org = await create_org(mallory)
    project = (
        await alice.post(f"/api/orgs/{alice_org['id']}/projects", json={"name": "Secret"})
    ).json()
    r = await mallory.get(f"/api/orgs/{mallory_org['id']}/projects/{project['id']}")
    assert r.status_code == 404
    r = await mallory.get(
        f"/api/orgs/{mallory_org['id']}/projects/{project['id']}/environments"
    )
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("role", "can_manage_projects", "can_update_org"),
    [
        (Role.ADMIN, True, False),
        (Role.DEVELOPER, False, False),
        (Role.VIEWER, False, False),
    ],
)
async def test_role_permissions(new_user, role, can_manage_projects, can_update_org):
    owner, _ = await new_user()
    member, member_user = await new_user()
    org = await create_org(owner)
    await add_member(org["id"], member_user["id"], role)
    base = f"/api/orgs/{org['id']}"

    assert (await member.get(base)).status_code == 200
    assert (await member.get(f"{base}/projects")).status_code == 200

    r = await member.post(f"{base}/projects", json={"name": "New"})
    assert (r.status_code == 201) is can_manage_projects

    r = await member.patch(base, json={"name": "Renamed"})
    assert (r.status_code == 200) is can_update_org
    if not can_update_org:
        assert r.status_code == 403


async def test_admin_cannot_grant_or_touch_owner(new_user):
    owner, owner_user = await new_user()
    admin, admin_user = await new_user()
    _, dev_user = await new_user()
    org = await create_org(owner)
    await add_member(org["id"], admin_user["id"], Role.ADMIN)
    dev_member = await add_member(org["id"], dev_user["id"], Role.DEVELOPER)
    members = (await owner.get(f"/api/orgs/{org['id']}/members")).json()
    owner_member = next(m for m in members if m["user_id"] == owner_user["id"])

    base = f"/api/orgs/{org['id']}/members"
    assert (await admin.patch(f"{base}/{dev_member}", json={"role": "viewer"})).status_code == 200
    assert (await admin.patch(f"{base}/{dev_member}", json={"role": "owner"})).status_code == 403
    r = await admin.patch(f"{base}/{owner_member['id']}", json={"role": "admin"})
    assert r.status_code == 403
    assert (await admin.delete(f"{base}/{owner_member['id']}")).status_code == 403


async def test_last_owner_cannot_be_demoted_or_leave(new_user):
    owner, owner_user = await new_user()
    org = await create_org(owner)
    members = (await owner.get(f"/api/orgs/{org['id']}/members")).json()
    me = members[0]["id"]
    base = f"/api/orgs/{org['id']}/members/{me}"
    r = await owner.patch(base, json={"role": "admin"})
    assert r.status_code == 400 and r.json()["detail"] == "last_owner"
    r = await owner.delete(base)
    assert r.status_code == 400

    _, second = await new_user()
    await add_member(org["id"], second["id"], Role.OWNER)
    assert (await owner.patch(base, json={"role": "admin"})).status_code == 200


async def test_member_can_leave(new_user):
    owner, _ = await new_user()
    viewer, viewer_user = await new_user()
    org = await create_org(owner)
    member_id = await add_member(org["id"], viewer_user["id"], Role.VIEWER)
    assert (await viewer.delete(f"/api/orgs/{org['id']}/members/{member_id}")).status_code == 204
    assert (await viewer.get(f"/api/orgs/{org['id']}")).status_code == 404


async def test_owner_can_delete_org(new_user):
    owner, _ = await new_user()
    org = await create_org(owner)
    await owner.post(f"/api/orgs/{org['id']}/projects", json={"name": "API"})
    assert (await owner.delete(f"/api/orgs/{org['id']}")).status_code == 204
    assert (await owner.get("/api/orgs")).json() == []
