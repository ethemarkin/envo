import httpx
import pytest

from app.main import create_app


@pytest.fixture
async def site(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("outside", encoding="utf-8")
    app = create_app(static_dir=str(tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


async def test_spa_routes_get_index_with_security_headers(site):
    for path in ("/", "/projects/123", "/invite/some-token", "/cli/authorize"):
        r = await site.get(path)
        assert r.status_code == 200, path
        assert "id=root" in r.text
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


async def test_assets_are_cached_forever(site):
    r = await site.get("/assets/index-abc123.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    assert "immutable" in r.headers["cache-control"]
    assert (await site.get("/assets/missing.js")).status_code == 404


async def test_root_files_and_no_path_traversal(site):
    assert (await site.get("/favicon.svg")).text == "<svg/>"
    r = await site.get("/..%2Fsecret.txt")
    assert "outside" not in r.text


async def test_api_routes_are_not_shadowed(site):
    assert (await site.get("/api/health")).json() == {"status": "ok"}
    r = await site.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    assert (await site.get("/api/auth/me")).status_code == 401


async def test_without_a_build_nothing_is_served():
    app = create_app(static_dir=None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        assert (await c.get("/")).status_code == 404
