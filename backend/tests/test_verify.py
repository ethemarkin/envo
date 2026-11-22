import os

from sqlalchemy import select, update

from app.core.crypto import LocalKeyProvider, get_key_provider
from app.core.db import SessionLocal
from app.modules.variables.models import Variable
from app.modules.variables.rotate import rewrap_deks
from app.modules.variables.verify import verify_all
from tests.conftest import create_project


async def fill(owner) -> None:
    project = await create_project(owner, "API")
    envs = (await owner.get(f"/api/projects/{project['id']}/environments")).json()
    for env in envs[:2]:
        base = f"/api/projects/{project['id']}/environments/{env['id']}"
        await owner.put(f"{base}/variables/A", json={"value": "1"})
        await owner.put(f"{base}/variables/A", json={"value": "2"})
        await owner.put(f"{base}/variables/B", json={"value": "3"})


async def verify(provider) -> object:
    async with SessionLocal() as s:
        return await verify_all(s, provider)


async def test_everything_decrypts_with_the_configured_key(new_user):
    owner, _ = await new_user()
    await fill(owner)
    report = await verify(get_key_provider())
    assert report.ok, report.failures
    assert (report.environments, report.variables, report.revisions) == (2, 4, 6)


async def test_wrong_master_key_is_reported_per_environment(new_user):
    owner, _ = await new_user()
    await fill(owner)
    wrong = LocalKeyProvider("test1", {"test1": os.urandom(32)})
    report = await verify(wrong)
    assert not report.ok
    assert len(report.failures) == 2
    assert all("cannot unwrap data key" in f for f in report.failures)
    assert report.variables == 0


async def test_rotated_keys_need_the_retired_key_until_rewrapped(new_user):
    owner, _ = await new_user()
    await fill(owner)
    old_key = get_key_provider()._keys["test1"]  # type: ignore[attr-defined]
    new_only = LocalKeyProvider("k2", {"k2": os.urandom(32)})
    both = LocalKeyProvider("k2", {"k2": new_only._keys["k2"], "test1": old_key})

    assert not (await verify(new_only)).ok
    assert (await verify(both)).ok
    async with SessionLocal() as s:
        await rewrap_deks(s, both)
    # After re-wrapping, the old key is no longer needed.
    assert (await verify(new_only)).ok


async def test_tampered_value_is_detected(new_user):
    owner, _ = await new_user()
    await fill(owner)
    async with SessionLocal() as s:
        var = (await s.scalars(select(Variable).where(Variable.key == "B"))).first()
        broken = bytearray(var.ciphertext)
        broken[-1] ^= 1
        await s.execute(
            update(Variable).where(Variable.id == var.id).values(ciphertext=bytes(broken))
        )
        await s.commit()
    report = await verify(get_key_provider())
    assert [f.split(":")[1].strip() for f in report.failures] == ["decryption failed"]
