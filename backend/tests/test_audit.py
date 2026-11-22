import uuid

from app.core.db import SessionLocal
from app.modules.auth.models import User
from app.modules.authorization.policy import Role
from tests.conftest import add_group_member, add_project_member, create_group, create_project


async def promote(user_id: str) -> None:
    async with SessionLocal() as s:
        (await s.get(User, uuid.UUID(user_id))).is_admin = True
        await s.commit()


async def test_project_audit_log(new_user):
    owner, _ = await new_user()
    project = await create_project(owner, "API")
    env = (await owner.get(f"/api/projects/{project['id']}/environments")).json()[0]
    base = f"/api/projects/{project['id']}/environments/{env['id']}"
    await owner.put(f"{base}/variables/SECRET", json={"value": "never-in-audit"})
    await owner.post(f"{base}/variables/reveal", json={})

    events = (await owner.get(f"/api/projects/{project['id']}/audit-events")).json()["events"]
    assert [e["action"] for e in events] == [
        "variables.revealed",
        "variables.updated",
        "project.created",
    ]
    assert events[0]["actor"]["type"] == "user" and events[0]["details"]["keys"] == ["SECRET"]
    assert "never-in-audit" not in str(events)

    only_vars = (
        await owner.get(f"/api/projects/{project['id']}/audit-events?action=variables.")
    ).json()["events"]
    assert {e["action"] for e in only_vars} == {"variables.revealed", "variables.updated"}


async def test_audit_pagination(new_user):
    owner, _ = await new_user()
    project = await create_project(owner, "API")
    env = (await owner.get(f"/api/projects/{project['id']}/environments")).json()[0]
    for i in range(4):
        await owner.put(
            f"/api/projects/{project['id']}/environments/{env['id']}/variables/K{i}",
            json={"value": "v"},
        )
    url = f"/api/projects/{project['id']}/audit-events?limit=2"
    seen = []
    before = None
    while True:
        page = (await owner.get(url + (f"&before={before}" if before else ""))).json()
        seen += [e["id"] for e in page["events"]]
        before = page["next_before"]
        if before is None:
            break
    assert len(seen) == len(set(seen)) == 5  # 4 writes + project.created


async def test_group_audit_log_covers_the_subtree(new_user):
    owner, _ = await new_user()
    acme = await create_group(owner, "Acme")
    team = await create_group(owner, "Team", acme["id"])
    nested = await create_project(owner, "Nested", team["id"])
    outside = await create_project(owner, "Outside")

    events = (await owner.get(f"/api/groups/{acme['id']}/audit-events")).json()["events"]
    project_ids = {e["project_id"] for e in events if e["project_id"]}
    assert nested["id"] in project_ids and outside["id"] not in project_ids
    assert {e["action"] for e in events} >= {"group.created", "project.created"}

    team_events = (await owner.get(f"/api/groups/{team['id']}/audit-events")).json()["events"]
    assert all(e["group_id"] != acme["id"] or e["project_id"] for e in team_events)


async def test_audit_log_is_for_owners_and_admins(new_user):
    owner, _ = await new_user()
    dev, dev_user = await new_user()
    admin, admin_user = await new_user()
    group = await create_group(owner, "Acme")
    project = await create_project(owner, "API", group["id"])
    await add_group_member(group["id"], dev_user["id"], Role.DEVELOPER)
    await add_project_member(project["id"], admin_user["id"], Role.ADMIN)

    assert (await dev.get(f"/api/projects/{project['id']}/audit-events")).status_code == 403
    assert (await dev.get(f"/api/groups/{group['id']}/audit-events")).status_code == 403
    assert (await admin.get(f"/api/projects/{project['id']}/audit-events")).status_code == 200
    # A project admin has no role on the group itself.
    assert (await admin.get(f"/api/groups/{group['id']}/audit-events")).status_code == 404


async def test_instance_audit_log_for_administrators(new_user, client):
    user, me = await new_user()
    await client.post(
        "/api/auth/login", json={"email": me["email"], "password": "wrong-password-x"}
    )
    assert (await user.get("/api/admin/audit-events")).status_code == 403
    await promote(me["id"])
    events = (await user.get("/api/admin/audit-events?action=auth.")).json()["events"]
    actions = [e["action"] for e in events]
    assert "auth.login_failed" in actions and "auth.signup" in actions
    failed = next(e for e in events if e["action"] == "auth.login_failed")
    assert failed["details"] == {"email": me["email"]}
    assert "wrong-password" not in str(events)
