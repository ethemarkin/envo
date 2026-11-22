import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import CurrentUser, SessionDep
from app.modules.authorization.access import can_create_root, visible_tree
from app.modules.authorization.policy import Role

router = APIRouter(prefix="/api/tree", tags=["groups"])


class TreeNodeOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    path: str
    # None when the group is only listed as the path to an accessible child.
    role: Role | None


class TreeOut(BaseModel):
    groups: list[TreeNodeOut]
    projects: list[TreeNodeOut]
    can_create_root: bool


@router.get("", response_model=TreeOut)
async def get_tree(user: CurrentUser, session: SessionDep) -> TreeOut:
    """Everything the caller can reach, for the navigation tree and CLI lookups.
    For projects `parent_id` is the group id (null at the root)."""
    tree = await visible_tree(session, user)
    return TreeOut(
        groups=[TreeNodeOut(**n.__dict__) for n in tree.groups],
        projects=[TreeNodeOut(**n.__dict__) for n in tree.projects],
        can_create_root=await can_create_root(session, user),
    )
