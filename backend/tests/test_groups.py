import uuid

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.modules.auth.models import User
from app.modules.authorization.policy import Role
from tests.conftest import (
    add_group_member,
    add_project_member,
    create_group,
    create_project,
    make_client,
)


async def signup_admin(client) -> str:
    """Sign up and promote to instance administrator."""
    r = await client.post(
        "/api/auth/signup", json={"email": "boss@example.com", "password": "long-enough-pw"}
    )
    async with SessionLocal() as s:
        user = await s.get(User, uuid.UUID(r.json()["id"]))
        user.is_admin = True
        await s.commit()
    return r.json()["id"]


async def test_first_user_becomes_admin():
    async with SessionLocal() as s:
        await s.execute(delete(User))
        await s.commit()
    async with make_client() as first, make_client() as second:
        r1 = await first.post(
            "/api/auth/signup", json={"email": "a@example.com", "password": "long-enough-pw"}
        )
        r2 = await second.post(
            "/api/auth/signup", json={"email": "b@example.com", "password": "long-enough-pw"}
        )
        assert r1.json()["is_admin"] is True
        assert r2.json()["is_admin"] is False


async def test_nested_groups_paths_and_slugs(new_user):
    c, _ = await new_user()
    acme = await create_group(c, "Çağrı Yazılım")
    assert acme["slug"] == "cagri-yazilim" and acme["path"] == "cagri-yazilim"
    assert acme["role"] == "owner" and acme["ancestors"] == []

    backend = await create_group(c, "Backend", acme["id"])
    payments = await create_group(c, "Payments", backend["id"])
    assert payments["path"] == "cagri-yazilim/backend/payments"
    assert [a["slug"] for a in payments["ancestors"]] == ["cagri-yazilim", "backend"]

    project = await create_project(c, "Web API", payments["id"])
    assert project["path"] == "cagri-yazilim/backend/payments/web-api"
    assert [a["slug"] for a in project["ancestors"]] == ["cagri-yazilim", "backend", "payments"]

    # Groups and projects share one namespace per parent.
    r = await c.post(
        "/api/projects", json={"name": "X", "slug": "payments", "group_id": backend["id"]}
    )
    assert r.status_code == 409
    clash = await create_project(c, "Payments", backend["id"])
    assert clash["slug"] == "payments-2"
    # The same slug is fine under another parent.
    other = await create_group(c, "Backend", None)
    assert other["slug"] == "backend"

    children = (await c.get(f"/api/groups/{backend['id']}/children")).json()
    assert [(ch["type"], ch["slug"]) for ch in children] == [
        ("group", "payments"),
        ("project", "payments-2"),
    ]


async def test_root_projects_and_tree(new_user):
    c, _ = await new_user()
    solo = await create_project(c, "Solo")
    assert solo["group_id"] is None and solo["path"] == "solo" and solo["role"] == "owner"
    acme = await create_group(c, "Acme")
    sub = await create_group(c, "Infra", acme["id"])
    nested = await create_project(c, "Terraform", sub["id"])

    tree = (await c.get("/api/tree")).json()
    assert tree["can_create_root"] is True
    assert [(g["path"], g["role"]) for g in tree["groups"]] == [
        ("acme", "owner"),
        ("acme/infra", "owner"),
    ]
    assert [(p["path"], p["parent_id"]) for p in tree["projects"]] == [
        ("acme/infra/terraform", sub["id"]),
        ("solo", None),
    ]
    assert nested["role"] == "owner"


async def test_membership_is_inherited_downwards(new_user):
    owner, _ = await new_user()
    dev, dev_user = await new_user()
    acme = await create_group(owner, "Acme")
    team = await create_group(owner, "Team", acme["id"])
    project = await create_project(owner, "API", team["id"])
    unrelated = await create_group(owner, "Other")

    await add_group_member(acme["id"], dev_user["id"], Role.DEVELOPER)
    assert (await dev.get(f"/api/groups/{team['id']}")).json()["role"] == "developer"
    assert (await dev.get(f"/api/projects/{project['id']}")).json()["role"] == "developer"
    assert (await dev.get(f"/api/groups/{unrelated['id']}")).status_code == 404

    # A direct role lower in the tree raises the effective role there only.
    await add_project_member(project["id"], dev_user["id"], Role.ADMIN)
    assert (await dev.get(f"/api/projects/{project['id']}")).json()["role"] == "admin"
    assert (await dev.get(f"/api/groups/{team['id']}")).json()["role"] == "developer"

    tree = (await dev.get("/api/tree")).json()
    assert [g["path"] for g in tree["groups"]] == ["acme", "acme/team"]
    assert tree["can_create_root"] is True


async def test_project_member_sees_only_the_path_to_the_project(new_user):
    owner, _ = await new_user()
    guest, guest_user = await new_user()
    acme = await create_group(owner, "Acme")
    team = await create_group(owner, "Team", acme["id"])
    await create_project(owner, "Hidden", team["id"])
    shared = await create_project(owner, "Shared", team["id"])
    await add_project_member(shared["id"], guest_user["id"], Role.VIEWER)

    tree = (await guest.get("/api/tree")).json()
    assert [(g["path"], g["role"]) for g in tree["groups"]] == [("acme", None), ("acme/team", None)]
    assert [p["path"] for p in tree["projects"]] == ["acme/team/shared"]
    # Path groups are not themselves accessible.
    assert (await guest.get(f"/api/groups/{team['id']}")).status_code == 404


async def test_other_users_get_404(new_user):
    alice, _ = await new_user()
    mallory, _ = await new_user()
    group = await create_group(alice, "Acme")
    project = await create_project(alice, "API", group["id"])
    for method, path in [
        ("GET", f"/api/groups/{group['id']}"),
        ("PATCH", f"/api/groups/{group['id']}"),
        ("DELETE", f"/api/groups/{group['id']}"),
        ("GET", f"/api/groups/{group['id']}/members"),
        ("GET", f"/api/groups/{group['id']}/children"),
        ("GET", f"/api/projects/{project['id']}"),
        ("GET", f"/api/projects/{project['id']}/environments"),
        ("GET", f"/api/projects/{project['id']}/members"),
    ]:
        r = await mallory.request(method, path, json={} if method == "PATCH" else None)
        assert r.status_code == 404, (method, path, r.status_code)
    r = await mallory.post("/api/groups", json={"name": "Sneaky", "parent_id": group["id"]})
    assert r.status_code == 404
    r = await mallory.post("/api/projects", json={"name": "Sneaky", "group_id": group["id"]})
    assert r.status_code == 404
    assert (await mallory.get("/api/tree")).json()["groups"] == []


@pytest.mark.parametrize(
    ("role", "can_create_child", "can_update", "can_delete"),
    [
        (Role.ADMIN, True, True, False),
        (Role.DEVELOPER, False, False, False),
        (Role.VIEWER, False, False, False),
    ],
)
async def test_group_role_permissions(new_user, role, can_create_child, can_update, can_delete):
    owner, _ = await new_user()
    member, member_user = await new_user()
    group = await create_group(owner, "Acme")
    await add_group_member(group["id"], member_user["id"], role)
    base = f"/api/groups/{group['id']}"

    r = await member.post("/api/projects", json={"name": "New", "group_id": group["id"]})
    assert (r.status_code == 201) is can_create_child
    r = await member.post("/api/groups", json={"name": "Sub", "parent_id": group["id"]})
    assert (r.status_code == 201) is can_create_child
    r = await member.patch(base, json={"name": "Renamed"})
    assert (r.status_code == 200) is can_update
    r = await member.delete(base)
    assert (r.status_code == 204) is can_delete
    if not can_delete:
        assert r.status_code == 403


async def test_root_creation_setting(new_user):
    user, _ = await new_user()
    async with make_client() as admin:
        await signup_admin(admin)
        assert (await user.get("/api/admin/settings")).status_code == 403
        r = await admin.patch("/api/admin/settings", json={"allow_root_creation": False})
        assert r.json() == {"allow_root_creation": False}

        r = await user.post("/api/groups", json={"name": "Nope"})
        assert r.status_code == 403 and r.json()["detail"] == "root_creation_disabled"
        assert (await user.post("/api/projects", json={"name": "Nope"})).status_code == 403
        assert (await user.get("/api/tree")).json()["can_create_root"] is False

        # Admins can still create at the root and see everything.
        group = await create_group(admin, "Company")
        # Users can still work inside groups they belong to.
        me = (await user.get("/api/auth/me")).json()
        await add_group_member(group["id"], me["id"], Role.ADMIN)
        await create_project(user, "Inside", group["id"])


async def test_admin_sees_everything_and_manages_admins(new_user):
    alice, _ = await new_user()
    private = await create_project(alice, "Private")
    async with make_client() as admin:
        await signup_admin(admin)
        assert (await admin.get(f"/api/projects/{private['id']}")).json()["role"] == "owner"
        assert "private" in [p["path"] for p in (await admin.get("/api/tree")).json()["projects"]]

        users = (await admin.get("/api/admin/users")).json()
        alice_id = next(
            u["id"] for u in users if u["email"] != "boss@example.com" and not u["is_admin"]
        )
        r = await admin.patch(f"/api/admin/users/{alice_id}", json={"is_admin": True})
        assert r.json()["is_admin"] is True


async def test_members_add_update_remove_and_inherited_listing(new_user):
    owner, owner_user = await new_user()
    _, dev_user = await new_user()
    acme = await create_group(owner, "Acme")
    project = await create_project(owner, "API", acme["id"])

    r = await owner.post(
        f"/api/projects/{project['id']}/members",
        json={"email": dev_user["email"].upper(), "role": "developer"},
    )
    assert r.status_code == 201
    assert r.json()["type"] == "member"
    member = r.json()["member"]
    assert member["inherited"] is False and member["source_type"] == "project"

    r = await owner.post(
        f"/api/projects/{project['id']}/members",
        json={"email": dev_user["email"], "role": "viewer"},
    )
    assert r.status_code == 409

    listing = (await owner.get(f"/api/projects/{project['id']}/members")).json()
    assert [(m["email"], m["role"], m["inherited"], m["source_name"]) for m in listing] == [
        (dev_user["email"], "developer", False, "API"),
        (owner_user["email"], "owner", True, "Acme"),
    ]

    base = f"/api/projects/{project['id']}/members/{member['id']}"
    assert (await owner.patch(base, json={"role": "admin"})).json()["role"] == "admin"
    assert (await owner.delete(base)).status_code == 204


async def test_admin_cannot_grant_or_touch_owner(new_user):
    owner, owner_user = await new_user()
    admin, admin_user = await new_user()
    _, dev_user = await new_user()
    group = await create_group(owner, "Acme")
    await add_group_member(group["id"], admin_user["id"], Role.ADMIN)
    dev_member = await add_group_member(group["id"], dev_user["id"], Role.DEVELOPER)
    members = (await owner.get(f"/api/groups/{group['id']}/members")).json()
    owner_member = next(m for m in members if m["user_id"] == owner_user["id"])

    base = f"/api/groups/{group['id']}/members"
    assert (await admin.patch(f"{base}/{dev_member}", json={"role": "viewer"})).status_code == 200
    assert (await admin.patch(f"{base}/{dev_member}", json={"role": "owner"})).status_code == 403
    assert (
        await admin.patch(f"{base}/{owner_member['id']}", json={"role": "admin"})
    ).status_code == 403
    assert (await admin.delete(f"{base}/{owner_member['id']}")).status_code == 403


async def test_last_owner_of_top_level_group_is_kept(new_user):
    owner, _ = await new_user()
    group = await create_group(owner, "Acme")
    me = (await owner.get(f"/api/groups/{group['id']}/members")).json()[0]["id"]
    base = f"/api/groups/{group['id']}/members/{me}"
    r = await owner.patch(base, json={"role": "admin"})
    assert r.status_code == 400 and r.json()["detail"] == "last_owner"
    assert (await owner.delete(base)).status_code == 400

    _, second = await new_user()
    await add_group_member(group["id"], second["id"], Role.OWNER)
    assert (await owner.patch(base, json={"role": "admin"})).status_code == 200


async def test_deleting_a_group_deletes_its_subtree(new_user):
    owner, _ = await new_user()
    acme = await create_group(owner, "Acme")
    sub = await create_group(owner, "Sub", acme["id"])
    project = await create_project(owner, "API", sub["id"])
    assert (await owner.delete(f"/api/groups/{acme['id']}")).status_code == 204
    assert (await owner.get(f"/api/groups/{sub['id']}")).status_code == 404
    assert (await owner.get(f"/api/projects/{project['id']}")).status_code == 404
    assert (await owner.get("/api/tree")).json() == {
        "groups": [],
        "projects": [],
        "can_create_root": True,
    }
