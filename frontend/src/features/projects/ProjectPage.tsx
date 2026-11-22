import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { InlineCreate } from "../../app/InlineCreate";
import { del, get, patch, post } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import { canManage } from "../../lib/permissions";
import type { Environment, Project } from "../../lib/types";
import { orgKeys, useOrganization } from "../organizations/queries";

export function ProjectPage() {
  const { orgId = "", projectId = "" } = useParams();
  const base = `/api/orgs/${orgId}/projects/${projectId}`;
  const envKey = ["orgs", orgId, "projects", projectId, "environments"];
  const qc = useQueryClient();
  const navigate = useNavigate();

  const org = useOrganization(orgId);
  const project = useQuery({
    queryKey: ["orgs", orgId, "projects", projectId],
    queryFn: () => get<Project>(base),
  });
  const envs = useQuery({
    queryKey: envKey,
    queryFn: () => get<Environment[]>(`${base}/environments`),
  });

  const invalidateEnvs = () => qc.invalidateQueries({ queryKey: envKey });
  const createEnv = useMutation({
    mutationFn: (name: string) => post<Environment>(`${base}/environments`, { name }),
    onSuccess: invalidateEnvs,
  });
  const updateEnv = useMutation({
    mutationFn: ({ id, ...body }: { id: string; protected: boolean }) =>
      patch<Environment>(`${base}/environments/${id}`, body),
    onSettled: invalidateEnvs,
  });
  const deleteEnv = useMutation({
    mutationFn: (id: string) => del(`${base}/environments/${id}`),
    onSettled: invalidateEnvs,
  });
  const deleteProject = useMutation({
    mutationFn: () => del(base),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orgKeys.projects(orgId) });
      navigate(`/orgs/${orgId}`);
    },
  });

  if (project.isPending || org.isPending) return <Spinner />;
  if (project.error) return <ErrorNote>{errorMessage(project.error)}</ErrorNote>;
  if (org.error) return <ErrorNote>{errorMessage(org.error)}</ErrorNote>;

  const manage = canManage(org.data.role);
  const mutationError = updateEnv.error ?? deleteEnv.error ?? deleteProject.error;

  return (
    <div className="space-y-8">
      <div>
        <Link to={`/orgs/${orgId}`} className="text-sm text-zinc-500 hover:text-zinc-900">
          ← {org.data.name}
        </Link>
        <div className="mt-2 flex items-baseline gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{project.data.name}</h1>
          <span className="font-mono text-sm text-zinc-500">{project.data.slug}</span>
        </div>
        {project.data.description && (
          <p className="mt-1 text-sm text-zinc-600">{project.data.description}</p>
        )}
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Ortamlar</h2>
        {mutationError && <ErrorNote>{errorMessage(mutationError)}</ErrorNote>}
        {envs.isPending ? (
          <Spinner />
        ) : envs.error ? (
          <ErrorNote>{errorMessage(envs.error)}</ErrorNote>
        ) : (
          <ul className="card divide-y divide-zinc-100">
            {envs.data.map((env) => (
              <li key={env.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                <Link
                  to={`/orgs/${orgId}/projects/${projectId}/environments/${env.id}`}
                  className="group min-w-40 flex-1"
                >
                  <p className="font-medium group-hover:underline">{env.name}</p>
                  <p className="font-mono text-xs text-zinc-500">--env {env.slug}</p>
                </Link>
                {env.protected && (
                  <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
                    Korumalı
                  </span>
                )}
                <span className="text-xs text-zinc-400">rev {env.revision}</span>
                {manage && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="btn-secondary py-1.5 text-xs"
                      disabled={updateEnv.isPending}
                      onClick={() => updateEnv.mutate({ id: env.id, protected: !env.protected })}
                    >
                      {env.protected ? "Korumayı kaldır" : "Koru"}
                    </button>
                    <button
                      type="button"
                      className="btn-danger py-1.5 text-xs"
                      disabled={deleteEnv.isPending}
                      onClick={() => {
                        if (window.confirm(`"${env.name}" ortamı silinsin mi?`)) deleteEnv.mutate(env.id);
                      }}
                    >
                      Sil
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {manage && (
          <div className="card p-5">
            <InlineCreate
              placeholder="Yeni ortam adı (örn. QA)"
              submitLabel="Ortam ekle"
              pending={createEnv.isPending}
              error={createEnv.error}
              onCreate={(name, reset) => createEnv.mutate(name, { onSuccess: reset })}
            />
          </div>
        )}
        <p className="text-xs text-zinc-500">
          Değişkenleri düzenlemek için bir ortam seçin. Korumalı ortamlarda gizli değerleri
          yalnızca Owner ve Admin okuyup değiştirebilir.
        </p>
      </section>

      {manage && (
        <section className="card border-red-200 p-5">
          <h2 className="text-sm font-semibold text-red-800">Projeyi sil</h2>
          <p className="mt-1 text-sm text-zinc-600">Projenin tüm ortamları kalıcı olarak silinir.</p>
          <button
            type="button"
            className="btn-danger mt-3"
            disabled={deleteProject.isPending}
            onClick={() => {
              if (window.confirm(`"${project.data.name}" projesi silinsin mi?`)) deleteProject.mutate();
            }}
          >
            Projeyi sil
          </button>
        </section>
      )}
    </div>
  );
}
