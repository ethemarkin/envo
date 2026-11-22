"""Environment history and rollback.

History lists change sets with the keys they touched, never values. A
rollback computes the state at an earlier revision and applies the difference
as a new revision, so history is never rewritten.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.core.deps import SessionDep
from app.core.errors import not_found
from app.modules.audit_logs.actors import ActorLabels, ActorOut
from app.modules.authorization.policy import EnvAction
from app.modules.environments.models import Environment
from app.modules.variables.models import Visibility
from app.modules.variables.router import (
    Ctx,
    error_response,
    parse_if_match,
    write_out,
)
from app.modules.variables.schemas import WriteOut
from app.modules.variables.service import (
    SetOp,
    VariableError,
    apply_changes,
    environment_dek,
    load_variables,
)
from app.modules.versions.models import (
    ChangeAction,
    ChangeSource,
    EnvironmentRevision,
    VariableRevision,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/environments/{env_id}/revisions",
    tags=["history"],
)


class KeyChangeOut(BaseModel):
    key: str
    action: ChangeAction
    visibility: Visibility | None


class RevisionOut(BaseModel):
    revision: int
    created_at: datetime
    source: ChangeSource
    message: str | None
    actor: ActorOut
    changes: list[KeyChangeOut]


class RevisionPage(BaseModel):
    current_revision: int
    revisions: list[RevisionOut]
    # Pass as ?before= to get the next (older) page; null on the last page.
    next_before: int | None


@router.get("", response_model=RevisionPage)
async def list_revisions(
    ctx: Ctx,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: Annotated[int | None, Query(ge=1)] = None,
) -> RevisionPage:
    ctx.require(EnvAction.LIST)
    query = (
        select(EnvironmentRevision)
        .where(EnvironmentRevision.environment_id == ctx.env.id)
        .order_by(EnvironmentRevision.revision.desc())
        .limit(limit + 1)
    )
    if before is not None:
        query = query.where(EnvironmentRevision.revision < before)
    revisions = list(await session.scalars(query))
    has_more = len(revisions) > limit
    revisions = revisions[:limit]

    numbers = [r.revision for r in revisions]
    changes: dict[int, list[KeyChangeOut]] = {n: [] for n in numbers}
    if numbers:
        rows = await session.scalars(
            select(VariableRevision)
            .where(
                VariableRevision.environment_id == ctx.env.id,
                VariableRevision.revision.in_(numbers),
            )
            .order_by(VariableRevision.key)
        )
        for row in rows:
            changes[row.revision].append(
                KeyChangeOut(key=row.key, action=row.action, visibility=row.visibility)
            )

    labels = await ActorLabels.load(
        session,
        {r.actor_user_id for r in revisions if r.actor_user_id},
        {r.actor_token_id for r in revisions if r.actor_token_id},
    )
    return RevisionPage(
        current_revision=ctx.env.revision,
        revisions=[
            RevisionOut(
                revision=r.revision,
                created_at=r.created_at,
                source=r.source,
                message=r.message,
                actor=labels.actor(r.actor_user_id, r.actor_token_id),
                changes=changes[r.revision],
            )
            for r in revisions
        ],
        next_before=revisions[-1].revision if has_more else None,
    )


async def state_at(
    session: AsyncSession, env: Environment, revision: int
) -> dict[str, tuple[Visibility, str]]:
    """Every key's (visibility, value) as of `revision`."""
    rows = await session.scalars(
        select(VariableRevision)
        .where(VariableRevision.environment_id == env.id, VariableRevision.revision <= revision)
        .order_by(VariableRevision.key, VariableRevision.revision.desc())
        .ext(distinct_on(VariableRevision.key))
    )
    dek = environment_dek(env)
    state: dict[str, tuple[Visibility, str]] = {}
    for row in rows:
        if row.action == ChangeAction.DELETE:
            continue
        assert dek is not None and row.ciphertext is not None and row.visibility is not None
        state[row.key] = (row.visibility, decrypt_value(dek, env.id, row.key, row.ciphertext))
    return state


@router.post("/{revision}/rollback", response_model=WriteOut)
async def rollback(
    revision: int,
    ctx: Ctx,
    request: Request,
    session: SessionDep,
    if_match: Annotated[str | None, Header()] = None,
):
    """Restore the environment to how it was at `revision` (0 = empty)."""
    ctx.require(EnvAction.WRITE)
    current = ctx.env.revision
    if revision < 0 or revision > current:
        raise not_found("revision_not_found")
    expected = parse_if_match(if_match)
    if expected is not None and expected != current:
        return error_response(VariableError("revision_conflict", 409))

    target = await state_at(session, ctx.env, revision)
    existing = {v.key for v in await load_variables(session, ctx.env.id)}
    try:
        result = await apply_changes(
            session,
            request,
            env_id=ctx.env.id,
            group_id=ctx.project.group_id,
            project_id=ctx.project.id,
            actor_id=ctx.user_id,
            actor_token_id=ctx.token_id,
            source=ChangeSource.ROLLBACK,
            sets=[SetOp(k, value, vis) for k, (vis, value) in sorted(target.items())],
            deletes=sorted(existing - set(target)),
            # The diff was computed against this revision; refuse if it moved.
            expected_revision=current,
            message=f"rollback to {revision}",
        )
    except VariableError as e:
        return error_response(e)
    return write_out(result)
