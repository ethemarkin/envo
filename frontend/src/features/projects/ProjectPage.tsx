import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { Breadcrumbs } from "../../app/Breadcrumbs";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { InlineCreate } from "../../app/InlineCreate";
import { del, get, patch, post } from "../../lib/api";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { canManage } from "../../lib/permissions";
import type { Environment } from "../../lib/types";
import { MembersPanel } from "../navigation/MembersPanel";
import { NodeSettings } from "../navigation/NodeSettings";
import { useProject } from "../navigation/queries";
import { ServiceTokensPanel } from "../service-tokens/ServiceTokensPanel";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const base = `/api/projects/${projectId}/environments`;
  const envKey = ["projects", projectId, "environments"];
  const qc = useQueryClient();

  const envs = useQuery({ queryKey: envKey, queryFn: () => get<Environment[]>(base) });
  const invalidateEnvs = () => qc.invalidateQueries({ queryKey: envKey });
  const createEnv = useMutation({
    mutationFn: (name: string) => post<Environment>(base, { name }),
    onSuccess: invalidateEnvs,
  });
  const updateEnv = useMutation({
    mutationFn: ({ id, ...body }: { id: string; protected: boolean }) =>
      patch<Environment>(`${base}/${id}`, body),
    onSettled: invalidateEnvs,
  });
  const deleteEnv = useMutation({
    mutationFn: (id: string) => del(`${base}/${id}`),
    onSettled: invalidateEnvs,
  });

  if (project.isPending) return <Spinner />;
  if (project.error) return <ErrorNote>{errorMessage(project.error)}</ErrorNote>;
  const p = project.data;
  const manage = canManage(p.role);
  const mutationError = updateEnv.error ?? deleteEnv.error;

  return (
    <div className="space-y-10" key={p.id}>
      <div className="space-y-1">
        <Breadcrumbs items={p.ancestors} />
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
          <span className="font-mono text-sm text-zinc-500">{p.path}</span>
          <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
            {ROLE_LABELS[p.role]}
          </span>
        </div>
        {p.description && <p className="text-sm text-zinc-600">{p.description}</p>}
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
                <Link to={`/projects/${p.id}/environments/${env.id}`} className="group min-w-40 flex-1">
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
                        if (window.confirm(`"${env.name}" ortamı ve tüm değişkenleri silinsin mi?`)) {
                          deleteEnv.mutate(env.id);
                        }
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
          Korumalı ortamlarda gizli değerleri yalnızca Owner ve Admin okuyup değiştirebilir.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">CLI</h2>
        <p className="text-sm text-zinc-600">Bir çalışma dizinini bu projeye bağlamak için:</p>
        <pre className="card overflow-x-auto p-4 font-mono text-xs">
          envo init --project {p.path}
        </pre>
      </section>

      {manage && envs.data && <ServiceTokensPanel projectId={p.id} environments={envs.data} />}

      <MembersPanel kind="projects" id={p.id} role={p.role} />

      <NodeSettings
        key={`${p.id}-${p.slug}-${p.name}`}
        kind="projects"
        id={p.id}
        name={p.name}
        slug={p.slug}
        path={p.path}
        description={p.description}
        canUpdate={manage}
        canDelete={p.role === "owner"}
        afterDelete={p.group_id ? `/groups/${p.group_id}` : "/"}
      />
    </div>
  );
}
