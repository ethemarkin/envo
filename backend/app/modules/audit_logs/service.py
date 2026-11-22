import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_logs.models import AuditEvent


def record(
    session: AsyncSession,
    request: Request | None,
    action: str,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the session; it commits with the caller's transaction.

    `details` must never contain variable values, passwords or tokens.
    """
    ip = user_agent = None
    if request is not None:
        ip = request.client.host if request.client else None
        user_agent = (request.headers.get("user-agent") or "")[:500] or None
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            user_agent=user_agent,
            details=details or {},
        )
    )
