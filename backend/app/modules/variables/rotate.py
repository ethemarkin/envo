"""Master key (KEK) rotation: re-wrap every environment's data key with the
current KEK. Values are not re-encrypted.

    1. Set the new key as ENVO_MASTER_KEY / ENVO_MASTER_KEY_ID and move the old
       one to ENVO_RETIRED_MASTER_KEYS ("old_id:base64").
    2. python -m app.modules.variables.rotate
    3. Once it reports 0 remaining, the old key can be removed.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import KeyProvider, get_key_provider
from app.modules.environments.models import Environment


async def rewrap_deks(session: AsyncSession, provider: KeyProvider) -> int:
    current = provider.current_kek_id
    envs = await session.scalars(
        select(Environment)
        .where(Environment.wrapped_dek.is_not(None), Environment.kek_id != current)
        .with_for_update()
    )
    count = 0
    for env in envs:
        assert env.wrapped_dek is not None and env.kek_id is not None
        dek = provider.unwrap_dek(env.id, env.kek_id, env.wrapped_dek)
        env.kek_id, env.wrapped_dek = provider.wrap_dek(env.id, dek)
        count += 1
    await session.commit()
    return count


async def main() -> None:
    from app.core.db import SessionLocal, engine

    async with SessionLocal() as session:
        count = await rewrap_deks(session, get_key_provider())
    await engine.dispose()
    print(f"re-wrapped {count} environment key(s); 0 remaining on old master keys")


if __name__ == "__main__":
    asyncio.run(main())
