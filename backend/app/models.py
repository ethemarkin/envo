"""Imports every model so Alembic and the metadata see all tables."""

from app.core.db import Base
from app.modules.audit_logs.models import AuditEvent
from app.modules.auth.models import RefreshToken, User, UserIdentity
from app.modules.environments.models import Environment
from app.modules.organizations.models import Membership, Organization
from app.modules.projects.models import Project
from app.modules.variables.models import Variable
from app.modules.versions.models import EnvironmentRevision, VariableRevision

__all__ = [
    "AuditEvent",
    "Base",
    "Environment",
    "EnvironmentRevision",
    "Membership",
    "Organization",
    "Project",
    "RefreshToken",
    "User",
    "UserIdentity",
    "Variable",
    "VariableRevision",
]
