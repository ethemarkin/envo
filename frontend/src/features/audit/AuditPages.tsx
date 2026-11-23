import { Link, useParams } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { useGroup, useProject } from "../navigation/queries";
import { AuditLog } from "./AuditLog";

export function ProjectAuditPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  if (project.isPending) return <Spinner />;
  if (project.error) return <ErrorNote>{errorMessage(project.error)}</ErrorNote>;
  return (
    <div className="space-y-2">
      <Link to={`/projects/${projectId}`} className="text-sm text-zinc-500 hover:text-zinc-900">
        ← {project.data.path}
      </Link>
      <AuditLog endpoint={`/api/projects/${projectId}/audit-events`} title="Audit log" />
    </div>
  );
}

export function GroupAuditPage() {
  const { groupId = "" } = useParams();
  const group = useGroup(groupId);
  if (group.isPending) return <Spinner />;
  if (group.error) return <ErrorNote>{errorMessage(group.error)}</ErrorNote>;
  return (
    <div className="space-y-2">
      <Link to={`/groups/${groupId}`} className="text-sm text-zinc-500 hover:text-zinc-900">
        ← {group.data.path}
      </Link>
      <AuditLog
        endpoint={`/api/groups/${groupId}/audit-events`}
        title="Audit log (including subgroups and projects)"
      />
    </div>
  );
}

export function InstanceAuditPage() {
  return (
    <div className="space-y-2">
      <Link to="/settings" className="text-sm text-zinc-500 hover:text-zinc-900">
        ← Settings
      </Link>
      <AuditLog endpoint="/api/admin/audit-events" title="Instance audit log" />
    </div>
  );
}
