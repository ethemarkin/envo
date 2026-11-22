"""Variable writes, reads and the bookkeeping that goes with them.

Every write runs in one transaction with the environment row locked:
validate -> plan the diff -> bump the revision -> update `variables` ->
append history -> audit event -> commit. A failed validation changes nothing.
"""

import uuid
from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value, generate_dek, get_key_provider
from app.modules.audit_logs.service import record
from app.modules.environments.models import Environment
from app.modules.variables.dotenv import MAX_VALUE_LENGTH, valid_key
from app.modules.variables.models import Variable, Visibility
from app.modules.versions.models import (
    ChangeAction,
    ChangeSource,
    EnvironmentRevision,
    VariableRevision,
)

DEFAULT_VISIBILITY = Visibility.SECRET


class VariableError(Exception):
    def __init__(self, code: str, status: int = 400, keys: list[str] | None = None) -> None:
        self.code = code
        self.status = status
        self.keys = keys or []


@dataclass(frozen=True)
class SetOp:
    key: str
    value: str | None = None  # None: keep the current value (visibility-only change)
    visibility: Visibility | None = None  # None: keep current, or default for new keys


@dataclass(frozen=True)
class Planned:
    key: str
    action: ChangeAction
    value: str | None
    visibility: Visibility | None


@dataclass
class WriteResult:
    revision: int
    changes: list[Planned] = field(default_factory=list)

    def keys(self, action: ChangeAction) -> list[str]:
        return [c.key for c in self.changes if c.action == action]


# --- Keys and decryption ---------------------------------------------------


def environment_dek(env: Environment) -> bytes | None:
    if env.wrapped_dek is None or env.kek_id is None:
        return None
    return get_key_provider().unwrap_dek(env.id, env.kek_id, env.wrapped_dek)


def ensure_dek(env: Environment) -> bytes:
    dek = environment_dek(env)
    if dek is None:
        dek = generate_dek()
        env.kek_id, env.wrapped_dek = get_key_provider().wrap_dek(env.id, dek)
    return dek


async def load_variables(session: AsyncSession, env_id: uuid.UUID) -> list[Variable]:
    rows = await session.scalars(
        select(Variable).where(Variable.environment_id == env_id).order_by(Variable.key)
    )
    return list(rows)


def decrypt_all(env: Environment, variables: list[Variable]) -> dict[str, str]:
    dek = environment_dek(env)
    if dek is None:
        return {}
    return {v.key: decrypt_value(dek, env.id, v.key, v.ciphertext) for v in variables}


# --- Planning --------------------------------------------------------------


def validate_ops(sets: list[SetOp], deletes: list[str]) -> None:
    keys = [s.key for s in sets] + deletes
    bad = [k for k in keys if not valid_key(k)]
    if bad:
        raise VariableError("invalid_key", 422, bad)
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise VariableError("duplicate_key", 422, dupes)
    too_long = [s.key for s in sets if s.value is not None and len(s.value) > MAX_VALUE_LENGTH]
    if too_long:
        raise VariableError("value_too_long", 422, too_long)


def plan_changes(
    current: dict[str, tuple[Visibility, str]], sets: list[SetOp], deletes: list[str]
) -> list[Planned]:
    """Diff requested operations against the current state. Unchanged keys are dropped."""
    missing_values = [s.key for s in sets if s.key not in current and s.value is None]
    if missing_values:
        raise VariableError("value_required", 422, missing_values)
    missing_keys = [k for k in deletes if k not in current]
    if missing_keys:
        raise VariableError("variable_not_found", 404, missing_keys)

    planned: list[Planned] = []
    for s in sets:
        if s.key not in current:
            planned.append(
                Planned(s.key, ChangeAction.CREATE, s.value, s.visibility or DEFAULT_VISIBILITY)
            )
            continue
        old_visibility, old_value = current[s.key]
        value = old_value if s.value is None else s.value
        visibility = s.visibility or old_visibility
        if value != old_value or visibility != old_visibility:
            planned.append(Planned(s.key, ChangeAction.UPDATE, value, visibility))
    planned += [Planned(k, ChangeAction.DELETE, None, None) for k in deletes]
    return planned


# --- Writing ---------------------------------------------------------------


async def lock_environment(session: AsyncSession, env_id: uuid.UUID) -> Environment:
    env = await session.scalar(
        select(Environment)
        .where(Environment.id == env_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert env is not None
    return env


async def apply_changes(
    session: AsyncSession,
    request: Request | None,
    *,
    env_id: uuid.UUID,
    group_id: uuid.UUID | None,
    project_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    source: ChangeSource,
    actor_token_id: uuid.UUID | None = None,
    sets: list[SetOp],
    deletes: list[str] | None = None,
    expected_revision: int | None = None,
    dry_run: bool = False,
    message: str | None = None,
) -> WriteResult:
    deletes = deletes or []
    validate_ops(sets, deletes)

    env = await lock_environment(session, env_id)
    if expected_revision is not None and expected_revision != env.revision:
        await session.commit()
        raise VariableError("revision_conflict", 409)

    variables = {v.key: v for v in await load_variables(session, env.id)}
    plaintext = decrypt_all(env, list(variables.values()))
    current = {k: (v.visibility, plaintext[k]) for k, v in variables.items()}
    try:
        planned = plan_changes(current, sets, deletes)
    except VariableError:
        await session.commit()
        raise

    if dry_run or not planned:
        # Nothing was modified; committing just releases the row lock (a
        # rollback would expire loaded objects, which async code cannot reload).
        await session.commit()
        return WriteResult(env.revision, planned)

    dek = ensure_dek(env)
    env.revision += 1
    session.add(
        EnvironmentRevision(
            environment_id=env.id,
            revision=env.revision,
            actor_user_id=actor_id,
            actor_token_id=actor_token_id,
            source=source,
            message=message,
        )
    )
    for change in planned:
        ciphertext = None
        if change.action == ChangeAction.DELETE:
            await session.delete(variables[change.key])
        else:
            assert change.value is not None and change.visibility is not None
            ciphertext = encrypt_value(dek, env.id, change.key, change.value)
            var = variables.get(change.key)
            if var is None:
                var = Variable(environment_id=env.id, key=change.key)
                session.add(var)
            var.visibility = change.visibility
            var.ciphertext = ciphertext
            var.updated_by_id = actor_id
        session.add(
            VariableRevision(
                environment_id=env.id,
                revision=env.revision,
                key=change.key,
                action=change.action,
                visibility=change.visibility,
                ciphertext=ciphertext,
            )
        )

    result = WriteResult(env.revision, planned)
    record(
        session,
        request,
        "variables.updated",
        actor_user_id=actor_id,
        actor_token_id=actor_token_id,
        group_id=group_id,
        project_id=project_id,
        resource_type="environment",
        resource_id=env.id,
        details={
            "environment": env.slug,
            "revision": env.revision,
            "source": source.value,
            "created": result.keys(ChangeAction.CREATE),
            "updated": result.keys(ChangeAction.UPDATE),
            "deleted": result.keys(ChangeAction.DELETE),
        },
    )
    await session.commit()
    return result
