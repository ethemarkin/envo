import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.slugs import slugify, unique_slug
from app.modules.audit_logs.service import record
from app.modules.authorization.deps import MembershipDep, ensure
from app.modules.authorization.policy import Action, Role, can_assign_role
from app.modules.organizations.models import Membership, Organization
from app.modules.organizations.schemas import (
    MemberOut,
    MemberUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
)

router = APIRouter(prefix="/api/orgs", tags=["organizations"])


def org_out(org: Organization, role: Role) -> OrganizationOut:
    return OrganizationOut(
        id=org.id, name=org.name, slug=org.slug, role=role, created_at=org.created_at
    )


def member_out(m: Membership) -> MemberOut:
    return MemberOut(
        id=m.id,
        user_id=m.user_id,
        email=m.user.email,
        name=m.user.name,
        role=m.role,
        created_at=m.created_at,
    )


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(user: CurrentUser, session: SessionDep):
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.name)
    )
    return [org_out(org, role) for org, role in rows.all()]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationCreate, user: CurrentUser, session: SessionDep):
    async def taken(slug: str) -> bool:
        found = await session.scalar(select(Organization.id).where(Organization.slug == slug))
        return found is not None

    if body.slug:
        if await taken(body.slug):
            raise conflict("slug_taken")
        slug = body.slug
    else:
        slug = await unique_slug(slugify(body.name, "org"), taken)

    org = Organization(name=body.name, slug=slug)
    session.add(org)
    await session.flush()
    session.add(Membership(organization_id=org.id, user_id=user.id, role=Role.OWNER))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    return org_out(org, Role.OWNER)


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(membership: MembershipDep, session: SessionDep):
    ensure(membership, Action.ORG_READ)
    org = await session.get(Organization, membership.organization_id)
    assert org is not None
    return org_out(org, membership.role)


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    body: OrganizationUpdate, membership: MembershipDep, session: SessionDep
):
    ensure(membership, Action.ORG_UPDATE)
    org = await session.get(Organization, membership.organization_id)
    assert org is not None
    if body.name is not None:
        org.name = body.name
    if body.slug is not None:
        org.slug = body.slug
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise conflict("slug_taken") from None
    return org_out(org, membership.role)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(membership: MembershipDep, session: SessionDep) -> None:
    ensure(membership, Action.ORG_DELETE)
    org = await session.get(Organization, membership.organization_id)
    await session.delete(org)
    await session.commit()


# --- Members -----------------------------------------------------------------


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(membership: MembershipDep, session: SessionDep):
    ensure(membership, Action.MEMBER_READ)
    members = await session.scalars(
        select(Membership)
        .where(Membership.organization_id == membership.organization_id)
        .order_by(Membership.created_at)
    )
    return [member_out(m) for m in members]


async def _get_member(session: SessionDep, org_id: uuid.UUID, member_id: uuid.UUID) -> Membership:
    target = await session.scalar(
        select(Membership)
        .where(Membership.id == member_id, Membership.organization_id == org_id)
        .with_for_update()
    )
    if target is None:
        raise not_found("member_not_found")
    return target


async def _owner_count(session: SessionDep, org_id: uuid.UUID) -> int:
    # Lock the owner rows so two concurrent demotions cannot leave zero owners.
    owners = await session.scalars(
        select(Membership.id)
        .where(Membership.organization_id == org_id, Membership.role == Role.OWNER)
        .with_for_update()
    )
    return len(owners.all())


@router.patch("/{org_id}/members/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    membership: MembershipDep,
    request: Request,
    session: SessionDep,
):
    org_id = membership.organization_id
    target = await _get_member(session, org_id, member_id)
    if not can_assign_role(membership.role, target.role, body.role):
        raise forbidden()
    if target.role == Role.OWNER and body.role != Role.OWNER:
        if await _owner_count(session, org_id) <= 1:
            raise bad_request("last_owner")
    previous = target.role
    target.role = body.role
    record(
        session,
        request,
        "member.role_changed",
        actor_user_id=membership.user_id,
        organization_id=org_id,
        resource_type="member",
        resource_id=target.id,
        details={"user_id": str(target.user_id), "from": previous.value, "to": body.role.value},
    )
    await session.commit()
    return member_out(target)


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID, membership: MembershipDep, request: Request, session: SessionDep
) -> None:
    org_id = membership.organization_id
    target = await _get_member(session, org_id, member_id)
    leaving_self = target.user_id == membership.user_id
    if not leaving_self and not can_assign_role(membership.role, target.role, None):
        raise forbidden()
    if target.role == Role.OWNER and await _owner_count(session, org_id) <= 1:
        raise bad_request("last_owner")
    record(
        session,
        request,
        "member.left" if leaving_self else "member.removed",
        actor_user_id=membership.user_id,
        organization_id=org_id,
        resource_type="member",
        resource_id=target.id,
        details={"user_id": str(target.user_id), "role": target.role.value},
    )
    await session.delete(target)
    await session.commit()
