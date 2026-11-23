"""Config files: files other than .env (application.properties, config.json,
...) placed in the project tree, with their own content in every environment,
kept in history, rollback and folder moves like variables."""

import pytest

from app.core.crypto import get_key_provider
from app.core.db import SessionLocal
from app.modules.authorization.policy import Role
from app.modules.folders.paths import InvalidPath, label, normalize_name
from app.modules.variables.verify import verify_all
from tests.conftest import add_group_member
from tests.test_folders import make_project, read_env, save_env

PROPS = "server.port=8080\nspring.datasource.password=s3cret\n"
PLACE = {"path": "backend", "name": "application.properties"}
JSON = '{\n  "apiKey": "abc",\n  "nested": {"a": [1, 2]}\n}\n'


def file_url(p, name: str, slug: str = "development") -> str:
    return f"{p.env(slug)}/files/{name}"


async def write_file(c, p, path: str, name: str, content: str, slug="development", **headers):
    return await c.put(
        file_url(p, name, slug), params={"path": path}, json={"content": content}, headers=headers
    )


async def read_file(c, p, path: str, name: str, slug="development") -> str:
    r = await c.get(file_url(p, name, slug), params={"path": path})
    assert r.status_code == 200, r.text
    return r.text


def test_file_names_and_labels():
    assert normalize_name(" application.properties ") == "application.properties"
    for bad in ("", ".", "..", "a/b", "a b", "a:b"):
        with pytest.raises(InvalidPath):
            normalize_name(bad)
    assert label("backend", "file:config.json") == "backend/config.json"
    assert label("", "file:config.json") == "config.json"
    assert label("backend", "PORT") == "backend/PORT"


async def test_place_write_and_read_config_files(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    r = await c.post(f"{p.folders}/files", json=PLACE)
    assert r.status_code == 201, r.text
    body = r.json()
    assert {"path": "backend", "name": "application.properties"} in body["files"]
    assert {"path": "", "name": ".env"} in body["files"]
    assert "backend" in body["folders"]
    # A .env is not created alongside it.
    assert body["env_files"] == [""]

    r = await c.post(f"{p.folders}/files", json=PLACE)
    assert r.status_code == 409 and r.json()["detail"] == "file_exists"
    for bad in ("a/b", "..", ""):
        r = await c.post(f"{p.folders}/files", json={"path": "", "name": bad})
        assert r.status_code == 422 and r.json()["detail"] == "invalid_file_name"

    # Empty until written, in every environment.
    assert await read_file(c, p, "backend", "application.properties") == ""
    r = await write_file(c, p, "backend", "application.properties", PROPS)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == ["backend/application.properties"]
    assert await read_file(c, p, "backend", "application.properties") == PROPS
    assert await read_file(c, p, "backend", "application.properties", "staging") == ""

    # Content is stored as written (no parsing), and unchanged writes are no-ops.
    revision = r.json()["revision"]
    r = await write_file(c, p, "backend", "application.properties", PROPS)
    assert r.json() == {"revision": revision, "created": [], "updated": [], "deleted": []}

    # Writing a file the project does not have places it (like a .env push).
    r = await write_file(c, p, "web", "config.json", JSON, "production")
    assert r.status_code == 200, r.text
    assert await read_file(c, p, "web", "config.json", "production") == JSON
    files = (await c.get(p.folders)).json()["files"]
    assert {"path": "web", "name": "config.json"} in files

    # The .env endpoints never see file contents, and vice versa.
    await save_env(c, p, "backend", "PORT=1\n")
    assert await read_env(c, p, "backend") == {"PORT": "1"}
    r = await save_env(c, p, "backend", "OTHER=2\n")
    assert r.status_code == 200
    assert await read_file(c, p, "backend", "application.properties") == PROPS
    listing = (await c.get(f"{p.env()}/variables")).json()
    assert [(v["path"], v["key"]) for v in listing["variables"]] == [("backend", "OTHER")]
    assert [(f["path"], f["name"]) for f in listing["files"]] == [
        ("backend", "application.properties")
    ]
    r = await c.post(f"{p.env()}/variables/reveal", params={"path": "backend"}, json={})
    assert set(r.json()["values"]) == {"OTHER"}

    # .env is not a config file.
    r = await write_file(c, p, "", ".env", "A=1")
    assert r.status_code == 422 and r.json()["detail"] == "invalid_file_name"

    # Empty content clears the file; it stays placed.
    r = await write_file(c, p, "backend", "application.properties", "")
    assert r.json()["deleted"] == ["backend/application.properties"]
    assert await read_file(c, p, "backend", "application.properties") == ""
    files = (await c.get(p.folders)).json()["files"]
    assert {"path": "backend", "name": "application.properties"} in files


async def test_file_writes_are_versioned_and_rolled_back(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    r = await write_file(c, p, "", "config.json", '{"v": 1}')
    first = r.json()["revision"]
    r = await write_file(c, p, "", "config.json", '{"v": 2}', **{"If-Match": f'"{first}"'})
    assert r.status_code == 200
    # Stale writer: refused.
    r = await write_file(c, p, "", "config.json", '{"v": 3}', **{"If-Match": f'"{first}"'})
    assert r.status_code == 409 and r.json()["detail"] == "revision_conflict"

    latest = (await c.get(f"{p.env()}/revisions")).json()["revisions"][0]
    assert latest["message"] == "edit config.json"
    assert latest["changes"] == [
        {
            "path": "",
            "key": "config.json",
            "kind": "file",
            "action": "update",
            "visibility": "secret",
        }
    ]

    r = await c.post(f"{p.env()}/revisions/{first}/rollback")
    assert r.status_code == 200, r.text
    assert await read_file(c, p, "", "config.json") == '{"v": 1}'

    # Too large.
    r = await write_file(c, p, "", "big.txt", "x" * (256 * 1024 + 1))
    assert r.status_code == 422 and r.json()["detail"] == "value_too_long"

    async with SessionLocal() as session:
        assert (await verify_all(session, get_key_provider())).ok


async def test_files_move_and_delete_with_their_folder(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    await write_file(c, p, "backend", "application.properties", PROPS)
    await write_file(c, p, "backend", "application.properties", "prod=1\n", "production")
    await save_env(c, p, "backend", "PORT=1\n")

    r = await c.patch(p.folders, json={"path": "backend", "new_path": "apps/api"})
    assert r.status_code == 200, r.text
    assert {"path": "apps/api", "name": "application.properties"} in r.json()["files"]
    assert await read_file(c, p, "apps/api", "application.properties") == PROPS
    assert await read_file(c, p, "apps/api", "application.properties", "production") == "prod=1\n"
    assert await read_env(c, p, "apps/api") == {"PORT": "1"}

    # Removing one file leaves the folder's .env alone.
    r = await c.delete(
        f"{p.folders}/files", params={"path": "apps/api", "name": "application.properties"}
    )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["environments"]) == ["development", "production"]
    assert {"path": "apps/api", "name": "application.properties"} not in r.json()["files"]
    assert await read_env(c, p, "apps/api") == {"PORT": "1"}
    assert await read_file(c, p, "apps/api", "application.properties") == ""

    # Removing the .env leaves files alone.
    await write_file(c, p, "apps/api", "config.json", JSON)
    r = await c.delete(f"{p.folders}/env", params={"path": "apps/api"})
    assert r.status_code == 200, r.text
    assert await read_file(c, p, "apps/api", "config.json") == JSON

    # Rolling back restores the removed file and places it again.
    history = (await c.get(f"{p.env()}/revisions")).json()["revisions"]
    before = next(h for h in history if h["message"] == "remove apps/api/application.properties")
    r = await c.post(f"{p.env()}/revisions/{before['revision'] - 1}/rollback")
    assert r.status_code == 200, r.text
    assert await read_file(c, p, "apps/api", "application.properties") == PROPS
    files = (await c.get(p.folders)).json()["files"]
    assert {"path": "apps/api", "name": "application.properties"} in files

    r = await c.delete(p.folders, params={"path": "apps"})
    assert r.status_code == 200, r.text
    assert r.json()["files"] == [{"path": "", "name": ".env"}]


async def test_files_and_folders_cannot_share_a_name(new_user):
    c, _ = await new_user()
    p = await make_project(c)
    await c.post(p.folders, json={"path": "config"})
    r = await c.post(f"{p.folders}/files", json={"path": "", "name": "config"})
    assert r.status_code == 409 and r.json()["detail"] == "folder_exists"
    await c.post(f"{p.folders}/files", json={"path": "", "name": "settings.json"})
    r = await c.post(p.folders, json={"path": "settings.json/x"})
    assert r.status_code == 409 and r.json()["detail"] == "file_exists"
    r = await c.patch(p.folders, json={"path": "config", "new_path": "settings.json"})
    assert r.status_code == 409 and r.json()["detail"] == "file_exists"


async def test_file_permissions(new_user):
    owner, _ = await new_user()
    p = await make_project(owner)
    await write_file(owner, p, "", "config.json", JSON)
    await write_file(owner, p, "", "config.json", JSON, "production")

    viewer, viewer_user = await new_user()
    await add_group_member(p.group["id"], viewer_user["id"], Role.VIEWER)
    r = await viewer.get(file_url(p, "config.json"))
    assert r.status_code == 403
    r = await write_file(viewer, p, "", "config.json", "{}")
    assert r.status_code == 403
    r = await viewer.post(f"{p.folders}/files", json={"path": "", "name": "x.yaml"})
    assert r.status_code == 403

    # Developers read and write unprotected environments, not production.
    dev, dev_user = await new_user()
    await add_group_member(p.group["id"], dev_user["id"], Role.DEVELOPER)
    assert await read_file(dev, p, "", "config.json") == JSON
    assert (await write_file(dev, p, "", "config.json", "{}")).status_code == 200
    r = await write_file(dev, p, "", "config.json", "{}", "production")
    assert r.status_code == 403
