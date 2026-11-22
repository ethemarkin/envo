"""Guards against new endpoints that forget authentication.

Every /api route is called anonymously and by a user who has no role on the
group or project in the URL. Only the explicitly public routes may answer
anything other than a refusal. (Service-token scoping is covered in
test_service_tokens.py.)
"""

import uuid

import pytest

from app.main import app
from tests.conftest import create_project, make_client

# (method, path) pairs that are public on purpose.
PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/registration"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/cli/auth/start"),
    ("POST", "/api/cli/auth/token"),
    ("POST", "/api/cli/auth/refresh"),
    ("POST", "/api/cli/auth/logout"),
    # The token in the link is the credential.
    ("GET", "/api/invitations/{token}"),
}

# Instance-wide routes a signed-in user without any role may still use.
ANY_USER = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout-all"),
    ("GET", "/api/tree"),
    ("POST", "/api/groups"),
    ("POST", "/api/projects"),
    ("GET", "/api/cli/auth/requests/{user_code}"),
    ("POST", "/api/cli/auth/approve"),
    ("POST", "/api/cli/auth/deny"),
    ("POST", "/api/invitations/{token}/accept"),
}


def api_routes() -> list[tuple[str, str]]:
    # The OpenAPI schema lists every operation, including nested routers.
    out = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/api"):
            out.extend((method.upper(), path) for method in operations)
    return sorted(out)


def fill(path: str, ids: dict[str, str]) -> str:
    for name in ("group_id", "project_id", "env_id", "member_id", "invitation_id", "token_id"):
        path = path.replace("{" + name + "}", ids.get(name, str(uuid.uuid4())))
    return (
        path.replace("{key}", "SOME_KEY")
        .replace("{user_code}", "BBBB-CCCC")
        .replace("{token}", "not-a-real-token")
        .replace("{user_id}", str(uuid.uuid4()))
    )


def test_every_route_is_classified():
    known = PUBLIC | ANY_USER
    routes = api_routes()
    assert len(routes) > 50 and any(p.startswith("/api/admin") for _, p in routes)
    # Everything else must be scoped to a group/project or the admin area.
    for method, path in routes:
        if (method, path) in known:
            continue
        assert any(
            seg in path
            for seg in ("{group_id}", "{project_id}", "/api/admin", "/api/service-tokens/self")
        ), f"{method} {path} is neither public, user-wide, nor scoped"


@pytest.mark.parametrize(("method", "path"), api_routes())
async def test_anonymous_requests_are_refused(method, path):
    if (method, path) in PUBLIC:
        pytest.skip("public route")
    async with make_client() as anon:
        r = await anon.request(method, fill(path, {}), json={} if method != "GET" else None)
    assert r.status_code == 401, (method, path, r.status_code, r.text)


@pytest.fixture
async def outsider_and_project(new_user):
    owner, _ = await new_user()
    project = await create_project(owner, "Private")
    env = (await owner.get(f"/api/projects/{project['id']}/environments")).json()[0]
    outsider, _ = await new_user()
    return outsider, {"project_id": project["id"], "env_id": env["id"]}


@pytest.mark.parametrize(("method", "path"), api_routes())
async def test_users_without_a_role_are_refused(method, path, outsider_and_project):
    if (method, path) in PUBLIC | ANY_USER:
        pytest.skip("not scoped")
    outsider, ids = outsider_and_project
    r = await outsider.request(method, fill(path, ids), json={} if method != "GET" else None)
    # Scoped resources are hidden (404); admin and token-only routes refuse.
    assert r.status_code in (401, 403, 404), (method, path, r.status_code, r.text)
