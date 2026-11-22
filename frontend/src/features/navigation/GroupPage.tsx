import { Link, useParams } from "react-router";
import { Breadcrumbs } from "../../app/Breadcrumbs";
import { EmptyState, ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { canManage } from "../../lib/permissions";
import { MembersPanel } from "./MembersPanel";
import { NodeSettings } from "./NodeSettings";
import { useGroup, useGroupChildren } from "./queries";

export function GroupPage() {
  const { groupId = "" } = useParams();
  const group = useGroup(groupId);
  const children = useGroupChildren(groupId);

  if (group.isPending) return <Spinner />;
  if (group.error) return <ErrorNote>{errorMessage(group.error)}</ErrorNote>;
  const g = group.data;
  const manage = canManage(g.role);

  return (
    <div className="space-y-10" key={g.id}>
      <div className="space-y-1">
        <Breadcrumbs items={g.ancestors} />
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{g.name}</h1>
          <span className="font-mono text-sm text-zinc-500">{g.path}</span>
          <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
            {ROLE_LABELS[g.role]}
          </span>
        </div>
        {g.description && <p className="text-sm text-zinc-600">{g.description}</p>}
        {manage && (
          <Link to={`/groups/${g.id}/audit`} className="inline-block pt-1 text-sm text-zinc-600 underline-offset-2 hover:underline">
            Denetim kaydı →
          </Link>
        )}
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Alt group'lar ve projeler</h2>
          {manage && (
            <div className="flex gap-2">
              <Link to={`/new?type=group&parent=${g.id}`} className="btn-secondary py-1.5">
                Yeni alt group
              </Link>
              <Link to={`/new?type=project&parent=${g.id}`} className="btn-primary py-1.5">
                Yeni proje
              </Link>
            </div>
          )}
        </div>
        {children.isPending ? (
          <Spinner />
        ) : children.error ? (
          <ErrorNote>{errorMessage(children.error)}</ErrorNote>
        ) : children.data.length === 0 ? (
          <EmptyState title="Bu group boş" />
        ) : (
          <ul className="card divide-y divide-zinc-100">
            {children.data.map((c) => (
              <li key={c.id}>
                <Link
                  to={c.type === "group" ? `/groups/${c.id}` : `/projects/${c.id}`}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-50"
                >
                  <span
                    className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                      c.type === "group" ? "bg-zinc-100 text-zinc-700" : "bg-sky-50 text-sky-800"
                    }`}
                  >
                    {c.type === "group" ? "Group" : "Proje"}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{c.name}</p>
                    {c.description && (
                      <p className="truncate text-xs text-zinc-500">{c.description}</p>
                    )}
                  </div>
                  <span className="ml-auto font-mono text-xs text-zinc-400">{c.slug}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <MembersPanel kind="groups" id={g.id} role={g.role} />

      <NodeSettings
        key={`${g.id}-${g.slug}-${g.name}`}
        kind="groups"
        id={g.id}
        name={g.name}
        slug={g.slug}
        path={g.path}
        description={g.description}
        canUpdate={manage}
        canDelete={g.role === "owner"}
        afterDelete={g.parent_id ? `/groups/${g.parent_id}` : "/"}
      />
    </div>
  );
}
