"""Variable writes, reads and the bookkeeping that goes with them.

Every write runs in one transaction with the environment row locked:
validate -> plan the diff -> bump the revision -> update `variables` ->
append history -> audit event -> commit. A failed validation changes nothing.

Variables are addressed by (path, key): `path` is the folder whose .env holds
the key ("" for the project root). A config file's content is stored the same
way under the key "file:<name>" (see folders.paths), so every write, history
entry and rollback covers both.
"""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import Request
from sqlalchemy import not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value, generate_dek, get_key_provider
from app.modules.audit_logs.service import record
from app.modules.environments.models import Environment
from app.modules.folders.models import ProjectFile, ProjectFolder
from app.modules.folders.paths import (
    ENV_FILE,
    FILE_KEY_PREFIX,
    ROOT,
    InvalidPath,
    ancestors,
    file_name,
    label,
    normalize_name,
    owner,
)
from app.modules.variables.dotenv import MAX_VALUE_LENGTH, valid_key
from app.modules.variables.models import Variable, Visibility
from app.modules.versions.models import (
    ChangeAction,
    ChangeSource,
    EnvironmentRevision,
    VariableRevision,
)

DEFAULT_VISIBILITY = Visibility.SECRET
MAX_FILE_SIZE = 256 * 1024

# Which stored keys to load: dotenv variables, config files, or both (None).
Kind = Literal["variables", "files"] | None

# (path, key)
Ref = tuple[str, str]


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
    path: str = ROOT

    @property
    def ref(self) -> Ref:
        return (self.path, self.key)


@dataclass(frozen=True)
class Planned:
    key: str
    action: ChangeAction
    value: str | None
    visibility: Visibility | None
    path: str = ROOT


@dataclass
class WriteResult:
    revision: int
    changes: list[Planned] = field(default_factory=list)

    def keys(self, action: ChangeAction) -> list[str]:
        """Changed variables as "KEY" (root folder) or "folder/KEY"."""
        return [label(c.path, c.key) for c in self.changes if c.action == action]


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


def is_file_key():
    return Variable.key.startswith(FILE_KEY_PREFIX, autoescape=True)


async def load_variables(
    session: AsyncSession, env_id: uuid.UUID, path: str | None = None, kind: Kind = None
) -> list[Variable]:
    """Stored keys of the environment in one folder, or (path=None) in all:
    dotenv variables, config files or (kind=None) both."""
    query = select(Variable).where(Variable.environment_id == env_id)
    if path is not None:
        query = query.where(Variable.path == path)
    if kind == "variables":
        query = query.where(not_(is_file_key()))
    elif kind == "files":
        query = query.where(is_file_key())
    rows = await session.scalars(query.order_by(Variable.path, Variable.key))
    return list(rows)


def decrypt_all(env: Environment, variables: list[Variable]) -> dict[Ref, str]:
    dek = environment_dek(env)
    if dek is None:
        return {}
    return {
        (v.path, v.key): decrypt_value(dek, env.id, v.key, v.ciphertext, v.path) for v in variables
    }


async def ensure_folders(session: AsyncSession, project_id: uuid.UUID, paths: set[str]) -> None:
    """Create the folders (and their parents) the project does not have yet."""
    wanted = {p for path in paths if path for p in [*ancestors(path), path]}
    if not wanted:
        return
    existing = set(
        await session.scalars(
            select(ProjectFolder.path).where(
                ProjectFolder.project_id == project_id, ProjectFolder.path.in_(wanted)
            )
        )
    )
    for path in sorted(wanted - existing):
        session.add(ProjectFolder(project_id=project_id, path=path))


async def ensure_files(
    session: AsyncSession, project_id: uuid.UUID, files: set[tuple[str, str]]
) -> None:
    """Place each (path, name) file (and create the folders it needs) where
    the project does not have it yet."""
    if not files:
        return
    paths = {path for path, _ in files}
    await ensure_folders(session, project_id, paths)
    rows = await session.execute(
        select(ProjectFile.path, ProjectFile.name).where(
            ProjectFile.project_id == project_id, ProjectFile.path.in_(paths)
        )
    )
    existing = {(path, name) for path, name in rows}
    for path, name in sorted(files - existing):
        session.add(ProjectFile(project_id=project_id, path=path, name=name))


async def ensure_env_files(session: AsyncSession, project_id: uuid.UUID, paths: set[str]) -> None:
    """Place a .env at each path where the project does not have one yet."""
    await ensure_files(session, project_id, {(path, ENV_FILE) for path in paths})


# --- Planning --------------------------------------------------------------


def valid_file_name(name: str) -> bool:
    try:
        return normalize_name(name) == name and name != ENV_FILE
    except InvalidPath:
        return False


def valid_stored_key(key: str) -> bool:
    name = file_name(key)
    return valid_key(key) if name is None else valid_file_name(name)


def too_long(key: str, value: str) -> bool:
    if file_name(key) is None:
        return len(value) > MAX_VALUE_LENGTH
    return len(value.encode()) > MAX_FILE_SIZE


def validate_ops(sets: list[SetOp], deletes: list[Ref]) -> None:
    refs = [s.ref for s in sets] + deletes
    bad = [label(*r) for r in refs if not valid_stored_key(r[1])]
    if bad:
        raise VariableError("invalid_key", 422, bad)
    dupes = sorted({label(*r) for r in refs if refs.count(r) > 1})
    if dupes:
        raise VariableError("duplicate_key", 422, dupes)
    too_long_keys = [
        label(*s.ref) for s in sets if s.value is not None and too_long(s.key, s.value)
    ]
    if too_long_keys:
        raise VariableError("value_too_long", 422, too_long_keys)


def plan_changes(
    current: dict[Ref, tuple[Visibility, str]], sets: list[SetOp], deletes: list[Ref]
) -> list[Planned]:
    """Diff requested operations against the current state. Unchanged keys are dropped."""
    missing_values = [label(*s.ref) for s in sets if s.ref not in current and s.value is None]
    if missing_values:
        raise VariableError("value_required", 422, missing_values)
    missing_keys = [label(*r) for r in deletes if r not in current]
    if missing_keys:
        raise VariableError("variable_not_found", 404, missing_keys)

    planned: list[Planned] = []
    for s in sets:
        if s.ref not in current:
            visibility = s.visibility or DEFAULT_VISIBILITY
            planned.append(Planned(s.key, ChangeAction.CREATE, s.value, visibility, s.path))
            continue
        old_visibility, old_value = current[s.ref]
        value = old_value if s.value is None else s.value
        visibility = s.visibility or old_visibility
        if value != old_value or visibility != old_visibility:
            planned.append(Planned(s.key, ChangeAction.UPDATE, value, visibility, s.path))
    planned += [Planned(k, ChangeAction.DELETE, None, None, p) for p, k in deletes]
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
    deletes: list[Ref] | None = None,
    expected_revision: int | None = None,
    dry_run: bool = False,
    message: str | None = None,
    commit: bool = True,
) -> WriteResult:
    """Apply `sets` and `deletes` to the environment as one revision.

    With commit=False the caller owns the transaction (e.g. a folder move that
    changes several environments at once): nothing is committed, and after an
    error the caller must roll back.
    """
    deletes = deletes or []
    validate_ops(sets, deletes)

    async def finish() -> None:
        # Committing just releases the row lock (a rollback would expire
        # loaded objects, which async code cannot reload).
        if commit:
            await session.commit()

    env = await lock_environment(session, env_id)
    if expected_revision is not None and expected_revision != env.revision:
        await finish()
        raise VariableError("revision_conflict", 409)

    variables = {(v.path, v.key): v for v in await load_variables(session, env.id)}
    plaintext = decrypt_all(env, list(variables.values()))
    current = {ref: (v.visibility, plaintext[ref]) for ref, v in variables.items()}
    try:
        planned = plan_changes(current, sets, deletes)
    except VariableError:
        await finish()
        raise

    if dry_run or not planned:
        await finish()
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
    await ensure_files(
        session,
        project_id,
        {(c.path, owner(c.key)) for c in planned if c.action != ChangeAction.DELETE},
    )
    for change in planned:
        if change.action == ChangeAction.DELETE:
            await session.delete(variables[(change.path, change.key)])
    # Flush deletes before inserts so a key can leave and re-enter a folder in
    # one write without tripping the unique constraint.
    await session.flush()
    for change in planned:
        ciphertext = None
        if change.action != ChangeAction.DELETE:
            assert change.value is not None and change.visibility is not None
            ciphertext = encrypt_value(dek, env.id, change.key, change.value, change.path)
            var = variables.get((change.path, change.key))
            if var is None:
                var = Variable(environment_id=env.id, path=change.path, key=change.key)
                session.add(var)
            var.visibility = change.visibility
            var.ciphertext = ciphertext
            var.updated_by_id = actor_id
        session.add(
            VariableRevision(
                environment_id=env.id,
                revision=env.revision,
                path=change.path,
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
    if commit:
        await session.commit()
    else:
        await session.flush()
    return result
