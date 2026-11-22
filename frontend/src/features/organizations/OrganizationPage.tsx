import { Link, useNavigate, useParams } from "react-router";
import { EmptyState, ErrorNote, Spinner } from "../../app/ErrorNote";
import { InlineCreate } from "../../app/InlineCreate";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { canManage } from "../../lib/permissions";
import {
  useCreateProject,
  useDeleteOrganization,
  useMembers,
  useOrganization,
  useProjects,
} from "./queries";

export function OrganizationPage() {
  const { orgId = "" } = useParams();
  const org = useOrganization(orgId);
  const projects = useProjects(orgId);
  const members = useMembers(orgId);
  const createProject = useCreateProject(orgId);
  const deleteOrg = useDeleteOrganization();
  const navigate = useNavigate();

  if (org.isPending) return <Spinner />;
  if (org.error) return <ErrorNote>{errorMessage(org.error)}</ErrorNote>;

  const role = org.data.role;

  return (
    <div className="space-y-8">
      <div>
        <Link to="/" className="text-sm text-zinc-500 hover:text-zinc-900">
          ← Organizasyonlar
        </Link>
        <div className="mt-2 flex items-baseline gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{org.data.name}</h1>
          <span className="font-mono text-sm text-zinc-500">{org.data.slug}</span>
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Projeler</h2>
        {canManage(role) && (
          <div className="card p-5">
            <InlineCreate
              placeholder="Yeni proje adı"
              submitLabel="Proje oluştur"
              pending={createProject.isPending}
              error={createProject.error}
              onCreate={(name, reset) =>
                createProject.mutate(
                  { name },
                  {
                    onSuccess: (p) => {
                      reset();
                      navigate(`/orgs/${orgId}/projects/${p.id}`);
                    },
                  },
                )
              }
            />
            <p className="mt-2 text-xs text-zinc-500">
              Her proje development, staging ve production ortamlarıyla oluşturulur.
            </p>
          </div>
        )}
        {projects.isPending ? (
          <Spinner />
        ) : projects.error ? (
          <ErrorNote>{errorMessage(projects.error)}</ErrorNote>
        ) : projects.data.length === 0 ? (
          <EmptyState title="Bu organizasyonda henüz proje yok" />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {projects.data.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/orgs/${orgId}/projects/${p.id}`}
                  className="card block p-4 transition-colors hover:border-zinc-400"
                >
                  <p className="font-medium">{p.name}</p>
                  <p className="font-mono text-xs text-zinc-500">{p.slug}</p>
                  {p.description && <p className="mt-2 text-sm text-zinc-600">{p.description}</p>}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Üyeler</h2>
        {members.isPending ? (
          <Spinner />
        ) : members.error ? (
          <ErrorNote>{errorMessage(members.error)}</ErrorNote>
        ) : (
          <ul className="card divide-y divide-zinc-100">
            {members.data.map((m) => (
              <li key={m.id} className="flex items-center justify-between px-5 py-3 text-sm">
                <div>
                  <p className="font-medium">{m.name ?? m.email}</p>
                  {m.name && <p className="text-zinc-500">{m.email}</p>}
                </div>
                <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
                  {ROLE_LABELS[m.role]}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-zinc-500">Üye daveti ve rol yönetimi ekip yönetimi fazında eklenecek.</p>
      </section>

      {role === "owner" && (
        <section className="card border-red-200 p-5">
          <h2 className="text-sm font-semibold text-red-800">Organizasyonu sil</h2>
          <p className="mt-1 text-sm text-zinc-600">
            Tüm projeler, ortamlar ve üyelikler kalıcı olarak silinir.
          </p>
          {deleteOrg.error && <ErrorNote>{errorMessage(deleteOrg.error)}</ErrorNote>}
          <button
            type="button"
            className="btn-danger mt-3"
            disabled={deleteOrg.isPending}
            onClick={() => {
              const typed = window.prompt(
                `Silmek için organizasyonun kısa adını yazın: ${org.data.slug}`,
              );
              if (typed === org.data.slug) {
                deleteOrg.mutate(orgId, { onSuccess: () => navigate("/") });
              }
            }}
          >
            Organizasyonu sil
          </button>
        </section>
      )}
    </div>
  );
}
