"""Invite-only sign-up and account administration."""

import re
import uuid

from sqlalchemy import delete

from app.core.db import SessionLocal
from app.modules.auth.models import User
from tests.conftest import create_project, make_client

PASSWORD = "long-enough-pw"


def token_from(mail) -> str:
    match = re.search(r"/invite/([A-Za-z0-9_-]+)", mail.text)
    assert match, mail.text
    return match.group(1)


async def make_admin(user_id: str) -> None:
    async with SessionLocal() as s:
        user = await s.get(User, uuid.UUID(user_id))
        user.is_admin = True
        await s.commit()


async def test_sign_up_needs_an_invitation(client):
    assert (await client.get("/api/auth/registration")).json() == {"invitation_required": True}
    body = {"email": "walk-in@example.com", "password": PASSWORD}
    r = await client.post("/api/auth/signup", json=body)
    assert r.status_code == 403 and r.json()["detail"] == "invitation_required"
    r = await client.post("/api/auth/signup", json={**body, "invite_token": "made-up"})
    assert r.status_code == 404 and r.json()["detail"] == "invitation_not_found"
    # No session was created.
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_empty_instance_is_open_for_the_first_account(client):
    async with SessionLocal() as s:
        await s.execute(delete(User))
        await s.commit()
    assert (await client.get("/api/auth/registration")).json() == {"invitation_required": False}
    r = await client.post(
        "/api/auth/signup", json={"email": "first@example.com", "password": PASSWORD}
    )
    assert r.status_code == 201 and r.json()["is_admin"] is True
    assert (await client.get("/api/auth/registration")).json() == {"invitation_required": True}


async def test_admin_invites_to_the_instance(new_user, outbox):
    admin, admin_user = await new_user()
    await make_admin(admin_user["id"])

    r = await admin.post("/api/admin/invitations", json={"email": " Newbie@Example.com "})
    assert r.status_code == 201, r.text
    assert r.json()["invitation"]["email"] == "newbie@example.com"
    assert r.json()["invite_url"] is None
    token = token_from(outbox[0])

    pending = (await admin.get("/api/admin/invitations")).json()
    assert [i["email"] for i in pending] == ["newbie@example.com"]

    async with make_client() as anon:
        preview = (await anon.get(f"/api/invitations/{token}")).json()
        assert preview["target_type"] == "instance" and preview["role"] is None
        assert preview["target_id"] is None and preview["email"] == "newbie@example.com"

        r = await anon.post(
            "/api/auth/signup",
            json={"email": "newbie@example.com", "password": PASSWORD, "invite_token": token},
        )
        assert r.status_code == 201, r.text
        assert r.json()["email_verified"] is True and r.json()["is_admin"] is False
        # Single use; no access to anything yet.
        assert (await anon.get(f"/api/invitations/{token}")).status_code == 404
        tree = (await anon.get("/api/tree")).json()
        assert tree["groups"] == [] and tree["projects"] == []

    assert (await admin.get("/api/admin/invitations")).json() == []
    # Existing accounts are not invited again.
    r = await admin.post("/api/admin/invitations", json={"email": "newbie@example.com"})
    assert r.status_code == 409 and r.json()["detail"] == "email_taken"


async def test_admin_invitation_reinvite_and_revoke(new_user, outbox):
    outbox.smtp = False
    admin, admin_user = await new_user()
    await make_admin(admin_user["id"])
    first = (await admin.post("/api/admin/invitations", json={"email": "x@example.com"})).json()
    second = (await admin.post("/api/admin/invitations", json={"email": "x@example.com"})).json()
    first_token = first["invite_url"].rsplit("/", 1)[1]
    second_token = second["invite_url"].rsplit("/", 1)[1]
    async with make_client() as anon:
        assert (await anon.get(f"/api/invitations/{first_token}")).status_code == 404
        assert (await anon.get(f"/api/invitations/{second_token}")).status_code == 200

    pending = (await admin.get("/api/admin/invitations")).json()
    assert len(pending) == 1
    r = await admin.delete(f"/api/admin/invitations/{pending[0]['id']}")
    assert r.status_code == 204
    async with make_client() as anon:
        r = await anon.post(
            "/api/auth/signup",
            json={"email": "x@example.com", "password": PASSWORD, "invite_token": second_token},
        )
        assert r.status_code == 404


async def test_only_admins_invite_and_delete(new_user):
    user, _ = await new_user()
    _, other = await new_user()
    assert (
        await user.post("/api/admin/invitations", json={"email": "y@example.com"})
    ).status_code == 403
    assert (await user.get("/api/admin/invitations")).status_code == 403
    assert (await user.delete(f"/api/admin/users/{other['id']}")).status_code == 403


async def test_admin_deletes_a_user(new_user):
    admin, admin_user = await new_user()
    await make_admin(admin_user["id"])
    victim, victim_user = await new_user("leaving@example.com")
    project = await create_project(victim, "Theirs")

    r = await admin.delete(f"/api/admin/users/{admin_user['id']}")
    assert r.status_code == 400 and r.json()["detail"] == "cannot_delete_self"
    assert (await admin.delete(f"/api/admin/users/{uuid.uuid4()}")).status_code == 404

    assert (await admin.delete(f"/api/admin/users/{victim_user['id']}")).status_code == 204
    # The session dies with the account, and the e-mail can be invited again.
    assert (await victim.get("/api/auth/me")).status_code == 401
    assert (await victim.post("/api/auth/refresh")).status_code == 401
    emails = [u["email"] for u in (await admin.get("/api/admin/users")).json()]
    assert "leaving@example.com" not in emails
    r = await admin.post("/api/admin/invitations", json={"email": "leaving@example.com"})
    assert r.status_code == 201
    # What they created stays; administrators still reach it.
    assert (await admin.get(f"/api/projects/{project['id']}")).status_code == 200

    async with make_client() as anon:
        r = await anon.post(
            "/api/auth/login", json={"email": "leaving@example.com", "password": PASSWORD}
        )
        assert r.status_code == 401
