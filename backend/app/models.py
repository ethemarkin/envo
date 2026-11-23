"""Imports every model so Alembic and the metadata see all tables."""

from app.core.db import Base
from app.modules.admin.models import InstanceSettings
from app.modules.audit_logs.models import AuditEvent
from app.modules.auth.cli_models import CliLoginRequest
from app.modules.auth.models import RefreshToken, User
from app.modules.environments.models import Environment
from app.modules.folders.models import ProjectFile, ProjectFolder
from app.modules.groups.invitation_models import Invitation
from app.modules.groups.models import Group, GroupMember
from app.modules.projects.models import Project, ProjectMember
from app.modules.service_tokens.models import ServiceToken, ServiceTokenEnvironment
from app.modules.variables.models import Variable
from app.modules.versions.models import EnvironmentRevision, VariableRevision

__all__ = [
    "AuditEvent",
    "Base",
    "CliLoginRequest",
    "Environment",
    "EnvironmentRevision",
    "Group",
    "GroupMember",
    "InstanceSettings",
    "Invitation",
    "Project",
    "ProjectFile",
    "ProjectFolder",
    "ProjectMember",
    "RefreshToken",
    "ServiceToken",
    "ServiceTokenEnvironment",
    "User",
    "Variable",
    "VariableRevision",
]
