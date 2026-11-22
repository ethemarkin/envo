"""Organization-scoped access.

Every org-scoped route resolves the caller's membership first. A missing
membership yields 404, not 403, so other tenants' resources are not even
confirmed to exist.
"""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import forbidden, not_found
from app.modules.authorization.policy import Action, can
from app.modules.organizations.models import Membership


async def get_membership(org_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Membership:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        raise not_found("organization_not_found")
    return membership


MembershipDep = Annotated[Membership, Depends(get_membership)]


def ensure(membership: Membership, action: Action) -> None:
    if not can(membership.role, action):
        raise forbidden()
