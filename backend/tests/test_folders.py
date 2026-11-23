"""Folders: one .env per folder and environment, a folder tree shared by all
environments, and folder moves/deletes recorded in each environment's history."""

import uuid

import pytest
from sqlalchemy import select, update

from app.core.crypto import (
    CryptoError,
    decrypt_value,
    encrypt_value,
    generate_dek,
    get_key_provider,
)
from app.core.crypto.envelope import value_aad
from app.core.db import SessionLocal
from app.modules.authorization.policy import Role
from app.modules.folders.paths import InvalidPath, normalize
from app.modules.variables.models import Variable
from app.modules.variables.verify import verify_all
from tests.conftest import add_group_member, create_group, create_project, make_client


class Project:
    def __init__(self, project: dict, group: dict, envs: list[dict]) -> None:
        self.project, self.group = project, group
        self.envs = {e["slug"]: e for e in envs}
        self.base = f"/api/projects/{project['id']}"
        self.folders = f"{self.base}/folders"

    def env(self, slug: str = "development") -> str:
        return f"{self.base}/environments/{self.envs[slug]['id']}"


async def make_project(c) -> Project:
    group = await create_group(c, "Acme")
    project = await create_project(c, "Shop", group["id"])
    envs = (await c.get(f"/api/projects/{project['id']}/environments")).json()
    return Project(project, group, envs)


async def save_env(c, p: Project, path: str, content: str, slug="development", **headers):
    return await c.post(
        f"{p.env(slug)}/import",
        params={"path": path},
        json={"content": content, "replace": True},
        headers=headers,
    )


async def read_env(c, p: Project, path: str, slug="development") -> dict[str, str]:
    r = await c.get(f"{p.env(slug)}/export", params={"path": path, "format": "json"})
    assert r.status_code == 200, r.text
    return r.json()


async def folders(c, p: Project) -> list[str]:
    r = await c.get(p.folders)
    assert r.status_code == 200, r.text
    return r.json()["folders"]


def test_paths_are_normalized_and_validated():
    assert normalize(None) == ""
    assert normalize(" /backend/ ") == "backend"
    assert normalize("services\\api//./web") == "services/api/web"
    assert normalize(".github") == ".github"
    for bad in ("..", "a/../b", "a b", "a:b", "x" * 256, "/".join(["a"] * 17)):
        with pytest.raises(InvalidPath):
            normalize(bad)


def test_root_aad_is_unchanged_and_folders_are_bound():
    env = uuid.uuid4()
    assert value_aad(env, "KEY") == f"envo:v1:{env}:KEY".encode()
    dek = generate_dek()
    sealed = encrypt_value(dek, env, "KEY", "v", "backend")
    assert decrypt_value(dek, env, "KEY", sealed, "backend") == "v"
    # A ciphertext copied to another folder (or the root) does not decrypt.
    for other in ("", "frontend"):
        with pytest.raises(CryptoError):
            decrypt_value(dek, env, "KEY", sealed, other)


async def test_each_folder_has_its_own_env_file(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    assert (await save_env(c, p, "", "PORT=80\nNAME=root\n")).status_code == 200
    assert (await save_env(c, p, "backend", "PORT=8000\n")).status_code == 200

    # The same key lives independently in each folder.
    assert await read_env(c, p, "") == {"PORT": "80", "NAME": "root"}
    assert await read_env(c, p, "backend") == {"PORT": "8000"}
    # Without ?path the export is the root .env (what `envo pull` reads).
    r = await c.get(f"{p.env()}/export", params={"format": "json"})
    assert r.json() == {"PORT": "80", "NAME": "root"}
    r = await c.get(f"{p.env()}/export", params={"path": "backend"})
    assert r.text == "PORT=8000\n"
    assert 'filename="shop.backend.development.env"' in r.headers["Content-Disposition"]

    # Writing into a folder creates it; other environments are untouched.
    assert await folders(c, p) == ["", "backend"]
    assert await read_env(c, p, "backend", "staging") == {}

    listing = (await c.get(f"{p.env()}/variables")).json()["variables"]
    assert [(v["path"], v["key"]) for v in listing] == [
        ("", "NAME"),
        ("", "PORT"),
        ("backend", "PORT"),
    ]
    only = (await c.get(f"{p.env()}/variables", params={"path": "backend"})).json()
    assert [v["key"] for v in only["variables"]] == ["PORT"]

    # Single-key endpoints take the folder too.
    r = await c.put(f"{p.env()}/variables/DEBUG", params={"path": "backend"}, json={"value": "1"})
    assert r.json()["created"] == ["backend/DEBUG"]
    r = await c.delete(f"{p.env()}/variables/PORT", params={"path": "backend"})
    assert r.json()["deleted"] == ["backend/PORT"]
    assert await read_env(c, p, "") == {"PORT": "80", "NAME": "root"}

    r = await c.get(f"{p.env()}/variables", params={"path": "../etc"})
    assert r.status_code == 422 and r.json()["detail"] == "invalid_path"


async def test_editor_save_replaces_the_folder_env(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    await save_env(c, p, "api", "A=1\nB=2\nC=3\n")
    await c.patch(
        f"{p.env()}/variables",
        params={"path": "api"},
        json={"upserts": [{"key": "A", "visibility": "visible"}]},
    )
    revision = (await c.get(f"{p.env()}/variables")).json()["revision"]

    r = await save_env(c, p, "api", "# comment\nA=10\nC=3\nD=4\n", **{"If-Match": f'"{revision}"'})
    assert r.status_code == 200, r.text
    items = {i["key"]: (i["status"], i["visibility"]) for i in r.json()["items"]}
    assert items == {
        "A": ("changed", "visible"),
        "C": ("unchanged", "secret"),
        "D": ("new", "secret"),
        "B": ("deleted", "secret"),
    }
    assert await read_env(c, p, "api") == {"A": "10", "C": "3", "D": "4"}

    # Stale editor: refused, nothing changed.
    r = await save_env(c, p, "api", "X=1\n", **{"If-Match": f'"{revision}"'})
    assert r.status_code == 409 and r.json()["detail"] == "revision_conflict"
    # Plain import still merges.
    r = await c.post(f"{p.env()}/import", params={"path": "api"}, json={"content": "E=5"})
    assert r.status_code == 200
    assert await read_env(c, p, "api") == {"A": "10", "C": "3", "D": "4", "E": "5"}

    history = (await c.get(f"{p.env()}/revisions")).json()["revisions"]
    assert history[1]["message"] == "edit .env"
    assert {(ch["path"], ch["key"], ch["action"]) for ch in history[1]["changes"]} == {
        ("api", "A", "update"),
        ("api", "B", "delete"),
        ("api", "D", "create"),
    }


async def test_create_folders(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    r = await c.post(p.folders, json={"path": "services/api"})
    assert r.status_code == 201, r.text
    assert r.json()["folders"] == ["", "services", "services/api"]
    r = await c.post(p.folders, json={"path": "/services/api/"})
    assert r.status_code == 409 and r.json()["detail"] == "folder_exists"
    for bad in ("", "/", "a/../b"):
        r = await c.post(p.folders, json={"path": bad})
        assert r.status_code == 422 and r.json()["detail"] == "invalid_path"
    body = (await c.get(p.folders)).json()
    assert body["can_manage"] is True


async def test_move_folder_moves_env_files_in_every_environment(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    await save_env(c, p, "backend", "DB=dev-db\n")
    await save_env(c, p, "backend/worker", "QUEUE=dev-q\n")
    await save_env(c, p, "backend", "DB=prod-db\n", "production")
    await save_env(c, p, "", "ROOT=1\n")
    await c.post(p.folders, json={"path": "backend/empty"})

    r = await c.patch(p.folders, json={"path": "backend", "new_path": "apps/api"})
    assert r.status_code == 200, r.text
    assert r.json()["folders"] == ["", "apps", "apps/api", "apps/api/empty", "apps/api/worker"]
    assert sorted(r.json()["environments"]) == ["development", "production"]

    assert await read_env(c, p, "apps/api") == {"DB": "dev-db"}
    assert await read_env(c, p, "apps/api/worker") == {"QUEUE": "dev-q"}
    assert await read_env(c, p, "apps/api", "production") == {"DB": "prod-db"}
    assert await read_env(c, p, "backend") == {}
    assert await read_env(c, p, "") == {"ROOT": "1"}

    latest = (await c.get(f"{p.env()}/revisions")).json()["revisions"][0]
    assert latest["message"] == "move backend -> apps/api"
    assert {(ch["path"], ch["key"], ch["action"]) for ch in latest["changes"]} == {
        ("backend", "DB", "delete"),
        ("backend/worker", "QUEUE", "delete"),
        ("apps/api", "DB", "create"),
        ("apps/api/worker", "QUEUE", "create"),
    }

    # Errors.
    r = await c.patch(p.folders, json={"path": "apps", "new_path": "apps/api/x"})
    assert r.status_code == 422 and r.json()["detail"] == "folder_into_itself"
    await c.post(p.folders, json={"path": "web"})
    r = await c.patch(p.folders, json={"path": "web", "new_path": "apps/api"})
    assert r.status_code == 409 and r.json()["detail"] == "folder_exists"
    r = await c.patch(p.folders, json={"path": "nope", "new_path": "other"})
    assert r.status_code == 404 and r.json()["detail"] == "folder_not_found"

    async with SessionLocal() as s:
        report = await verify_all(s, get_key_provider())
    assert report.ok, report.failures


async def test_delete_folder_and_rollback_restores_it(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    r = await save_env(c, p, "legacy", "OLD=1\n")
    before = r.json()["revision"]
    await save_env(c, p, "legacy/sub", "DEEP=2\n")
    await save_env(c, p, "", "KEEP=1\n")
    revision = (await c.get(f"{p.env()}/variables")).json()["revision"]

    r = await c.delete(p.folders, params={"path": "legacy"})
    assert r.status_code == 200, r.text
    assert r.json()["folders"] == [""]
    assert await read_env(c, p, "legacy") == {}
    assert await read_env(c, p, "") == {"KEEP": "1"}

    # Rolling back brings the values and the folders back.
    r = await c.post(f"{p.env()}/revisions/{revision}/rollback")
    assert r.status_code == 200, r.text
    assert await folders(c, p) == ["", "legacy", "legacy/sub"]
    assert await read_env(c, p, "legacy/sub") == {"DEEP": "2"}

    r = await c.post(f"{p.env()}/revisions/{before}/rollback")
    assert await read_env(c, p, "legacy") == {"OLD": "1"}
    assert await read_env(c, p, "legacy/sub") == {}
    assert await read_env(c, p, "") == {}

    r = await c.delete(p.folders, params={"path": ""})
    assert r.status_code == 422


async def test_folder_permissions(new_user):
    owner, _ = await new_user()
    p = await make_project(owner)
    await save_env(owner, p, "api", "A=1\n")
    await save_env(owner, p, "api", "A=prod\n", "production")

    dev, dev_user = await new_user()
    await add_group_member(p.group["id"], dev_user["id"], Role.DEVELOPER)
    viewer, viewer_user = await new_user()
    await add_group_member(p.group["id"], viewer_user["id"], Role.VIEWER)

    assert (await viewer.get(p.folders)).json()["can_manage"] is False
    r = await viewer.post(p.folders, json={"path": "web"})
    assert r.status_code == 403

    assert (await dev.post(p.folders, json={"path": "web"})).status_code == 201
    assert (await dev.patch(p.folders, json={"path": "web", "new_path": "site"})).status_code == 200
    # The folder holds values in protected production: developers cannot move it.
    r = await dev.patch(p.folders, json={"path": "api", "new_path": "server"})
    assert r.status_code == 403
    r = await dev.delete(p.folders, params={"path": "api"})
    assert r.status_code == 403
    assert await folders(owner, p) == ["", "api", "site"]
    assert await read_env(owner, p, "api", "production") == {"A": "prod"}
    assert await read_env(owner, p, "api") == {"A": "1"}


async def test_service_tokens_reach_folders_of_their_environments(new_user):
    owner, _ = await new_user()
    p = await make_project(owner)
    await save_env(owner, p, "worker", "Q=1\n")
    r = await owner.post(
        f"{p.base}/service-tokens",
        json={
            "name": "ci",
            "environment_ids": [p.envs["development"]["id"]],
            "expires_in_days": 30,
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    async with make_client() as bot:
        r = await bot.get(p.folders, headers=headers)
        assert r.json() == {
            "folders": ["", "worker"],
            "env_files": ["", "worker"],
            "can_manage": False,
        }
        r = await bot.get(
            f"{p.env()}/export", params={"path": "worker", "format": "json"}, headers=headers
        )
        assert r.json() == {"Q": "1"}
        r = await bot.post(p.folders, json={"path": "x"}, headers=headers)
        assert r.status_code in (401, 403)


async def test_moved_values_are_reencrypted_for_their_folder(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    await save_env(c, p, "a", "K=v\n")
    await c.patch(p.folders, json={"path": "a", "new_path": "b"})
    env_id = uuid.UUID(p.envs["development"]["id"])
    async with SessionLocal() as s:
        var = await s.scalar(select(Variable).where(Variable.environment_id == env_id))
        assert var is not None and var.path == "b"
        # Pretend the row were relabelled without re-encryption: it must fail.
        await s.execute(update(Variable).where(Variable.id == var.id).values(path="a"))
        await s.commit()
        report = await verify_all(s, get_key_provider())
    assert not report.ok


async def env_files(c, p: Project) -> list[str]:
    r = await c.get(p.folders)
    assert r.status_code == 200, r.text
    return r.json()["env_files"]


async def test_env_files_are_placed_per_project(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    # A new project has a .env at the root only; folders are structure.
    assert await env_files(c, p) == [""]
    r = await c.post(p.folders, json={"path": "services"})
    assert r.status_code == 201 and r.json()["env_files"] == [""]
    r = await c.post(p.folders, json={"path": "services/api", "env": True})
    assert r.json()["env_files"] == ["", "services/api"]

    r = await c.post(f"{p.folders}/env", json={"path": "services/web"})
    assert r.status_code == 201, r.text
    assert r.json()["folders"] == ["", "services", "services/api", "services/web"]
    assert r.json()["env_files"] == ["", "services/api", "services/web"]
    r = await c.post(f"{p.folders}/env", json={"path": "services/web/"})
    assert r.status_code == 409 and r.json()["detail"] == "env_file_exists"

    # Removing the root .env removes its values in every environment only.
    assert (await save_env(c, p, "", "ROOT=1\n")).status_code == 200
    assert (await save_env(c, p, "services/api", "API=1\n", slug="production")).status_code == 200
    r = await c.delete(f"{p.folders}/env", params={"path": ""})
    assert r.status_code == 200, r.text
    assert r.json()["env_files"] == ["services/api", "services/web"]
    assert r.json()["environments"] == ["development"]
    assert await read_env(c, p, "") == {}
    assert await read_env(c, p, "services/api", slug="production") == {"API": "1"}
    r = await c.delete(f"{p.folders}/env", params={"path": ""})
    assert r.status_code == 404 and r.json()["detail"] == "env_file_not_found"

    # Writing into a place without a .env (CLI push, rollback) adds one.
    assert (await save_env(c, p, "services", "S=1\n")).status_code == 200
    assert await env_files(c, p) == ["services", "services/api", "services/web"]


async def test_move_and_delete_carry_env_files(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    await c.post(p.folders, json={"path": "apps/api", "env": True})
    r = await c.patch(p.folders, json={"path": "apps", "new_path": "services"})
    assert r.status_code == 200, r.text
    assert r.json()["env_files"] == ["", "services/api"]
    r = await c.delete(p.folders, params={"path": "services"})
    assert r.status_code == 200, r.text
    assert r.json()["env_files"] == [""]


async def test_env_file_permissions(new_user):
    owner, _ = await new_user()
    p = await make_project(owner)
    await save_env(owner, p, "", "A=prod\n", "production")
    dev, dev_user = await new_user()
    await add_group_member(p.group["id"], dev_user["id"], Role.DEVELOPER)
    viewer, viewer_user = await new_user()
    await add_group_member(p.group["id"], viewer_user["id"], Role.VIEWER)

    assert (await viewer.post(f"{p.folders}/env", json={"path": "x"})).status_code == 403
    assert (await dev.post(f"{p.folders}/env", json={"path": "x"})).status_code == 201
    # The root .env holds values in protected production: developers cannot remove it.
    r = await dev.delete(f"{p.folders}/env", params={"path": ""})
    assert r.status_code == 403
    assert await env_files(owner, p) == ["", "x"]
