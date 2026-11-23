import { Link } from "react-router";
import { EmptyState, ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { useMe } from "../auth/useAuth";
import { useTree } from "./queries";

export function HomePage() {
  const { data: me } = useMe();
  const tree = useTree();

  if (tree.isPending) return <Spinner />;
  if (tree.error) return <ErrorNote>{errorMessage(tree.error)}</ErrorNote>;
  const { projects, can_create_root: canCreate } = tree.data;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Hello{me?.name ? `, ${me.name}` : ""}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Pick a group or project from the tree on the left.
        </p>
      </div>

      {canCreate && (
        <div className="flex flex-wrap gap-2">
          <Link to="/new?type=project" className="btn-primary">
            New project
          </Link>
          <Link to="/new?type=group" className="btn-secondary">
            New group
          </Link>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Projects you can access</h2>
        {projects.length === 0 ? (
          <EmptyState title="You don't have access to any projects yet">
            {canCreate
              ? "Create a project above or ask to be added to a group."
              : "Ask an admin to add you to a group or project."}
          </EmptyState>
        ) : (
          <ul className="card divide-y divide-zinc-100">
            {projects.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/projects/${p.id}`}
                  className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-zinc-50"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{p.name}</p>
                    <p className="truncate font-mono text-xs text-zinc-500">{p.path}</p>
                  </div>
                  {p.role && (
                    <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
                      {ROLE_LABELS[p.role]}
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
