import re
from datetime import timedelta

from sqlalchemy import update

from app.core.db import SessionLocal, utcnow
from app.modules.groups.invitation_models import Invitation
from tests.conftest import create_group, create_project, invite_token, make_client


def token_from(mail) -> str:
    match = re.search(r"/invite/([A-Za-z0-9_-]+)", mail.text)
    assert match, mail.text
    return match.group(1)


async def signup(c, email: str, token: str | None = None) -> dict:
    token = token or await invite_token(email)
    r = await c.post(
        "/api/auth/signup",
        json={"email": email, "password": "long-enough-pw", "invite_token": token},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_invite_new_user_to_group_and_accept(new_user, outbox):
    owner, _ = await new_user()
    acme = await create_group(owner, "Acme")
    sub = await create_group(owner, "Backend", acme["id"])
    project = await create_project(owner, "API", sub["id"])

    r = await owner.post(
        f"/api/groups/{acme['id']}/members", json={"email": "New@Example.com", "role": "developer"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "invitation" and body["invite_url"] is None
    assert body["invitation"]["email"] == "new@example.com"
    assert len(outbox) == 1 and outbox[0].to == "new@example.com"
    token = token_from(outbox[0])

    pending = (await owner.get(f"/api/groups/{acme['id']}/invitations")).json()
    assert [(i["email"], i["role"]) for i in pending] == [("new@example.com", "developer")]

    async with make_client() as anonymous:
        preview = (await anonymous.get(f"/api/invitations/{token}")).json()
        assert preview["target_type"] == "group" and preview["target_path"] == "acme"
        assert preview["role"] == "developer" and preview["email"] == "new@example.com"
        r = await anonymous.post(f"/api/invitations/{token}/accept")
        assert r.status_code == 401

    async with make_client() as invitee:
        # The invitation is the ticket to sign up; signing up with it accepts it.
        body = {"email": "new@example.com", "password": "long-enough-pw"}
        r = await invitee.post("/api/auth/signup", json=body)
        assert r.status_code == 403 and r.json()["detail"] == "invitation_required"
        r = await invitee.post(
            "/api/auth/signup", json={**body, "email": "other@example.com", "invite_token": token}
        )
        assert r.status_code == 403 and r.json()["detail"] == "invitation_email_mismatch"
        me = await signup(invitee, "new@example.com", token)
        assert me["email_verified"] is True
        # Inherited access to everything below the group.
        assert (await invitee.get(f"/api/projects/{project['id']}")).json()["role"] == "developer"
        assert (await invitee.get("/api/auth/me")).json()["email_verified"] is True
        # The link is single use.
        assert (await invitee.post(f"/api/invitations/{token}/accept")).status_code == 404

    assert (await owner.get(f"/api/groups/{acme['id']}/invitations")).json() == []


async def test_invitation_requires_matching_email(new_user, outbox):
    owner, _ = await new_user()
    project = await create_project(owner, "API")
    await owner.post(
        f"/api/projects/{project['id']}/members",
        json={"email": "right@example.com", "role": "viewer"},
    )
    token = token_from(outbox[0])
    async with make_client() as other:
        await signup(other, "wrong@example.com")
        r = await other.post(f"/api/invitations/{token}/accept")
        assert r.status_code == 403 and r.json()["detail"] == "invitation_email_mismatch"
        assert (await other.get(f"/api/projects/{project['id']}")).status_code == 404


async def test_without_smtp_the_link_is_returned(new_user, outbox):
    outbox.smtp = False
    owner, _ = await new_user()
    project = await create_project(owner, "API")
    r = await owner.post(
        f"/api/projects/{project['id']}/members", json={"email": "x@example.com", "role": "viewer"}
    )
    url = r.json()["invite_url"]
    assert url.startswith("http://localhost:5173/invite/")
    async with make_client() as anon:
        assert (await anon.get(f"/api/invitations/{url.rsplit('/', 1)[1]}")).status_code == 200


async def test_reinvite_replaces_and_revoke_invalidates(new_user, outbox):
    owner, _ = await new_user()
    project = await create_project(owner, "API")
    url = f"/api/projects/{project['id']}"
    await owner.post(f"{url}/members", json={"email": "x@example.com", "role": "viewer"})
    await owner.post(f"{url}/members", json={"email": "x@example.com", "role": "admin"})
    first, second = token_from(outbox[0]), token_from(outbox[1])
    async with make_client() as anon:
        assert (await anon.get(f"/api/invitations/{first}")).status_code == 404
        assert (await anon.get(f"/api/invitations/{second}")).json()["role"] == "admin"

    pending = (await owner.get(f"{url}/invitations")).json()
    assert len(pending) == 1
    assert (await owner.delete(f"{url}/invitations/{pending[0]['id']}")).status_code == 204
    async with make_client() as anon:
        assert (await anon.get(f"/api/invitations/{second}")).status_code == 404


async def test_expired_invitation(new_user, outbox):
    owner, _ = await new_user()
    project = await create_project(owner, "API")
    await owner.post(
        f"/api/projects/{project['id']}/members", json={"email": "x@example.com", "role": "viewer"}
    )
    async with SessionLocal() as s:
        await s.execute(update(Invitation).values(expires_at=utcnow() - timedelta(seconds=1)))
        await s.commit()
    async with make_client() as anon:
        assert (await anon.get(f"/api/invitations/{token_from(outbox[0])}")).status_code == 404


async def test_invitations_need_member_management_rights(new_user, outbox):
    from app.modules.authorization.policy import Role
    from tests.conftest import add_project_member

    owner, _ = await new_user()
    dev, dev_user = await new_user()
    admin, admin_user = await new_user()
    project = await create_project(owner, "API")
    await add_project_member(project["id"], dev_user["id"], Role.DEVELOPER)
    await add_project_member(project["id"], admin_user["id"], Role.ADMIN)
    url = f"/api/projects/{project['id']}"

    r = await dev.post(f"{url}/members", json={"email": "x@example.com", "role": "viewer"})
    assert r.status_code == 403
    assert (await dev.get(f"{url}/invitations")).status_code == 403
    # Admins cannot invite owners.
    r = await admin.post(f"{url}/members", json={"email": "x@example.com", "role": "owner"})
    assert r.status_code == 403
    assert outbox == []
