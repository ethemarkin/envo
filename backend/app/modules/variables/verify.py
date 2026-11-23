"""Check that every stored value can be decrypted with the configured keys.

Run after restoring a backup (or rotating master keys) to prove that the
database and the master key belong together:

    python -m app.modules.variables.verify [--database NAME]

--database checks another database on the same server as ENVO_DATABASE_URL
(e.g. a freshly restored copy) without repeating the credentials.

Exit code 0 when everything decrypts, 1 otherwise. Only counts and ids are
printed, never values.
"""

import asyncio
import sys
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import CryptoError, KeyProvider, decrypt_value, get_key_provider
from app.modules.environments.models import Environment
from app.modules.folders.paths import label
from app.modules.variables.models import Variable
from app.modules.versions.models import VariableRevision


@dataclass
class VerifyReport:
    environments: int = 0
    variables: int = 0
    revisions: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


async def verify_all(session: AsyncSession, provider: KeyProvider) -> VerifyReport:
    report = VerifyReport()
    deks: dict[uuid.UUID, bytes] = {}
    # Environments whose key failed; their values are not reported one by one.
    broken: set[uuid.UUID] = set()

    for env in await session.scalars(select(Environment)):
        if env.wrapped_dek is None or env.kek_id is None:
            continue  # never written to; holds no values
        report.environments += 1
        try:
            deks[env.id] = provider.unwrap_dek(env.id, env.kek_id, env.wrapped_dek)
        except CryptoError as exc:
            broken.add(env.id)
            report.failures.append(
                f"environment {env.id}: cannot unwrap data key with master key "
                f"{env.kek_id!r} ({exc})"
            )

    def check(env_id: uuid.UUID, path: str, key: str, ciphertext: bytes, what: str) -> bool:
        if env_id in broken:
            return False
        dek = deks.get(env_id)
        if dek is None:
            broken.add(env_id)
            report.failures.append(f"environment {env_id}: has values but no data key")
            return False
        try:
            decrypt_value(dek, env_id, key, ciphertext, path)
            return True
        except CryptoError:
            report.failures.append(f"{what} {env_id}/{label(path, key)}: decryption failed")
            return False

    for var in await session.scalars(select(Variable)):
        if check(var.environment_id, var.path, var.key, var.ciphertext, "variable"):
            report.variables += 1

    revisions = await session.scalars(
        select(VariableRevision).where(VariableRevision.ciphertext.is_not(None))
    )
    for rev in revisions:
        assert rev.ciphertext is not None
        what = f"revision {rev.revision} of"
        if check(rev.environment_id, rev.path, rev.key, rev.ciphertext, what):
            report.revisions += 1
    return report


async def main(argv: list[str]) -> int:
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    if len(argv) == 2 and argv[0] == "--database":
        url = url.set(database=argv[1])
    elif argv:
        print("usage: python -m app.modules.variables.verify [--database NAME]")
        return 2
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as session:
            report = await verify_all(session, get_key_provider())
    finally:
        await engine.dispose()

    print(f"database: {url.database}")
    print(
        f"checked {report.environments} environment key(s), "
        f"{report.variables} variable(s), {report.revisions} history value(s)"
    )
    for failure in report.failures[:50]:
        print(f"FAIL {failure}")
    if len(report.failures) > 50:
        print(f"... and {len(report.failures) - 50} more")
    print("OK: all stored values decrypt" if report.ok else f"{len(report.failures)} failure(s)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
