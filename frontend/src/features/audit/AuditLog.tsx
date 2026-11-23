import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { get } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { AuditEvent, AuditPage } from "../../lib/types";
import { formatTime } from "../environments/HistoryPanel";

const ACTION_LABELS: Record<string, string> = {
  "auth.signup": "Created an account",
  "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in attempt",
  "auth.cli_login_approved": "Approved a CLI sign-in",
  "auth.password_changed": "Changed their password",
  "auth.password_change_failed": "Failed password change attempt",
  "group.created": "Created a group",
  "group.updated": "Updated the group",
  "group.deleted": "Deleted the group",
  "project.created": "Created a project",
  "project.updated": "Updated the project",
  "project.deleted": "Deleted the project",
  "environment.created": "Created an environment",
  "environment.updated": "Updated the environment",
  "environment.deleted": "Deleted the environment",
  "variables.updated": "Changed variables",
  "folder.created": "Added a folder",
  "folder.moved": "Moved a folder",
  "folder.deleted": "Deleted a folder",
  "folder.env_added": "Added a .env",
  "folder.env_removed": "Removed a .env",
  "folder.file_added": "Added a config file",
  "folder.file_removed": "Removed a config file",
  "variables.file_read": "Read a config file",
  "variables.revealed": "Viewed secret values",
  "variables.exported": "Exported values",
  "member.added": "Added a member",
  "member.invited": "Sent an invitation",
  "member.invitation_revoked": "Revoked an invitation",
  "member.invitation_accepted": "Accepted an invitation",
  "member.role_changed": "Changed a member's role",
  "member.removed": "Removed a member",
  "member.left": "Left",
  "service_token.created": "Created a service token",
  "service_token.revoked": "Revoked a service token",
  "admin.settings_updated": "Changed instance settings",
  "admin.user_updated": "Changed admin rights",
  "admin.user_deleted": "Deleted a user",
  "admin.user_invited": "Invited a user to the instance",
  "admin.invitation_revoked": "Revoked an instance invitation",
};

const FILTERS: { label: string; prefix: string }[] = [
  { label: "All", prefix: "" },
  { label: "Variables", prefix: "variables." },
  { label: "Membership", prefix: "member." },
  { label: "Tokens", prefix: "service_token." },
];

/** A compact, human summary of the event's details (they never hold values). */
function summary(e: AuditEvent): string {
  const d = e.details;
  const list = (v: unknown) => (Array.isArray(v) ? v.join(", ") : "");
  switch (e.action) {
    case "variables.updated": {
      const parts = [
        list(d.created) && `+ ${list(d.created)}`,
        list(d.updated) && `~ ${list(d.updated)}`,
        list(d.deleted) && `− ${list(d.deleted)}`,
      ].filter(Boolean);
      return `${d.environment ?? ""} rev ${d.revision ?? "?"}: ${parts.join("  ")}`;
    }
    case "variables.revealed":
      return `${d.environment ?? ""}: ${list(d.keys)}`;
    case "variables.exported":
      return `${d.environment ?? ""}${d.path ? ` ${d.path}/.env` : ""} (${d.format}, ${d.count} ${d.count === 1 ? "variable" : "variables"})`;
    case "folder.created":
    case "folder.deleted":
      return String(d.path ?? "");
    case "folder.env_added":
    case "folder.env_removed":
      return d.path ? `${d.path}/.env` : ".env";
    case "folder.file_added":
    case "folder.file_removed":
      return d.path ? `${d.path}/${d.name}` : String(d.name ?? "");
    case "variables.file_read":
      return `${d.environment ?? ""}: ${d.file ?? ""}`;
    case "folder.moved":
      return `${d.path} → ${d.new_path}`;
    case "member.role_changed":
      return `${d.from} → ${d.to}`;
    case "member.invited":
    case "member.invitation_revoked":
      return String(d.email ?? "");
    case "auth.login_failed":
      return String(d.email ?? "");
    case "auth.login":
      return String(d.method ?? "");
    case "service_token.created":
      return `${d.name} (${list(d.environments)}${d.can_write ? ", write" : ""})`;
    default:
      return typeof d.slug === "string" ? d.slug : typeof d.path === "string" ? d.path : "";
  }
}

export function AuditLog({ endpoint, title }: { endpoint: string; title: string }) {
  const [filter, setFilter] = useState("");
  const events = useInfiniteQuery({
    queryKey: ["audit", endpoint, filter],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: "50" });
      if (filter) params.set("action", filter);
      if (pageParam) params.set("before", pageParam);
      return get<AuditPage>(`${endpoint}?${params}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_before,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Change and access events. Variable values, passwords and tokens are never recorded.
        </p>
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter">
        {FILTERS.map((f) => (
          <button
            key={f.label}
            type="button"
            aria-pressed={filter === f.prefix}
            onClick={() => setFilter(f.prefix)}
            className={`rounded-full px-3 py-1 text-xs ${
              filter === f.prefix ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {events.isPending ? (
        <Spinner />
      ) : events.error ? (
        <ErrorNote>{errorMessage(events.error)}</ErrorNote>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Time</th>
                  <th className="px-4 py-2.5 font-medium">Who</th>
                  <th className="px-4 py-2.5 font-medium">Action</th>
                  <th className="px-4 py-2.5 font-medium">Details</th>
                  <th className="px-4 py-2.5 font-medium">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {events.data.pages.flatMap((p) => p.events).map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="whitespace-nowrap px-4 py-2.5 text-zinc-500">{formatTime(e.created_at)}</td>
                    <td className="whitespace-nowrap px-4 py-2.5">
                      {e.actor.label}
                      {e.actor.type === "token" && (
                        <span className="ml-1 rounded bg-zinc-100 px-1 text-[11px] text-zinc-600">token</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">{ACTION_LABELS[e.action] ?? e.action}</td>
                    <td className="max-w-md break-words px-4 py-2.5 font-mono text-xs text-zinc-600">
                      {summary(e)}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-zinc-500">{e.ip ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.data.pages[0]?.events.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-zinc-500">No events.</p>
            )}
          </div>
          {events.hasNextPage && (
            <button
              type="button"
              className="btn-secondary"
              disabled={events.isFetchingNextPage}
              onClick={() => events.fetchNextPage()}
            >
              Older events
            </button>
          )}
        </>
      )}
    </div>
  );
}
