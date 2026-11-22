from datetime import timedelta

from sqlalchemy import update

from app.core.db import SessionLocal, utcnow
from app.modules.auth.cli_models import CliLoginRequest
from tests.conftest import make_client


async def start(client, name="laptop") -> dict:
    r = await client.post("/api/cli/auth/start", json={"client_name": name})
    assert r.status_code == 200, r.text
    return r.json()


async def poll(client, device_code: str):
    return await client.post("/api/cli/auth/token", json={"device_code": device_code})


async def test_full_login_flow(new_user):
    browser, user = await new_user()
    async with make_client() as cli:
        flow = await start(cli)
        assert flow["verification_uri"].endswith("/cli/authorize")
        assert "user_code" not in flow["verification_uri"]
        assert len(flow["user_code"]) == 9 and flow["user_code"][4] == "-"

        r = await poll(cli, flow["device_code"])
        assert r.status_code == 400 and r.json()["detail"] == "authorization_pending"

        # The user types the code (any case, with or without dash).
        typed = flow["user_code"].replace("-", "").lower()
        details = await browser.get(f"/api/cli/auth/requests/{typed}")
        assert details.status_code == 200
        assert details.json()["client_name"] == "laptop"
        assert (
            await browser.post("/api/cli/auth/approve", json={"user_code": typed})
        ).status_code == 204

        r = await poll(cli, flow["device_code"])
        assert r.status_code == 200
        tokens = r.json()
        assert tokens["user"]["id"] == user["id"]
        assert "set-cookie" not in r.headers

        # The device code is single use.
        assert (await poll(cli, flow["device_code"])).json()["detail"] == "invalid_grant"

        auth = {"Authorization": f"Bearer {tokens['access_token']}"}
        assert (await cli.get("/api/auth/me", headers=auth)).status_code == 200
        # Bearer requests need no CSRF header.
        assert (
            await cli.post("/api/orgs", json={"name": "CLI Org"}, headers=auth)
        ).status_code == 201

        r = await cli.post("/api/cli/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 200
        rotated = r.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]

        assert (
            await cli.post("/api/cli/auth/logout", json={"refresh_token": rotated["refresh_token"]})
        ).status_code == 204
        r = await cli.post(
            "/api/cli/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
        assert r.status_code == 401


async def test_denied_request(new_user):
    browser, _ = await new_user()
    async with make_client() as cli:
        flow = await start(cli)
        assert (
            await browser.post("/api/cli/auth/deny", json={"user_code": flow["user_code"]})
        ).status_code == 204
        assert (await poll(cli, flow["device_code"])).json()["detail"] == "access_denied"
        # A decided request cannot be approved afterwards.
        r = await browser.post("/api/cli/auth/approve", json={"user_code": flow["user_code"]})
        assert r.status_code == 404


async def test_expired_request(new_user):
    browser, _ = await new_user()
    async with make_client() as cli:
        flow = await start(cli)
        async with SessionLocal() as s:
            await s.execute(
                update(CliLoginRequest).values(expires_at=utcnow() - timedelta(seconds=1))
            )
            await s.commit()
        assert (await poll(cli, flow["device_code"])).json()["detail"] == "expired_token"
        r = await browser.post("/api/cli/auth/approve", json={"user_code": flow["user_code"]})
        assert r.status_code == 404


async def test_approval_requires_signed_in_user_and_csrf(new_user):
    async with make_client() as cli:
        flow = await start(cli)
        anonymous = await cli.post("/api/cli/auth/approve", json={"user_code": flow["user_code"]})
        assert anonymous.status_code == 401

    browser, _ = await new_user()
    r = await browser.post(
        "/api/cli/auth/approve",
        json={"user_code": flow["user_code"]},
        headers={"X-CSRF-Token": "forged"},
    )
    assert r.status_code == 403


async def test_unknown_codes(new_user):
    browser, _ = await new_user()
    assert (await browser.get("/api/cli/auth/requests/BBBB-CCCC")).status_code == 404
    async with make_client() as cli:
        assert (await poll(cli, "nope")).json()["detail"] == "invalid_grant"
