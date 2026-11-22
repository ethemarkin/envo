import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, get, getText, post } from "../../lib/api";
import type {
  Environment,
  ImportResult,
  VariableList,
  Visibility,
  WriteResult,
} from "../../lib/types";

export function envPaths(projectId: string, envId: string) {
  const project = `/api/projects/${projectId}`;
  const base = `${project}/environments/${envId}`;
  return {
    environments: `${project}/environments`,
    variables: `${base}/variables`,
    reveal: `${base}/variables/reveal`,
    import: `${base}/import`,
    export: `${base}/export`,
    key: ["projects", projectId, "environments", envId] as const,
    listKey: ["projects", projectId, "environments"] as const,
  };
}

export type EnvPaths = ReturnType<typeof envPaths>;

export function useEnvironment(paths: EnvPaths, envId: string) {
  return useQuery({
    queryKey: paths.listKey,
    queryFn: () => get<Environment[]>(paths.environments),
    select: (envs) => envs.find((e) => e.id === envId) ?? null,
  });
}

export function useVariables(paths: EnvPaths) {
  return useQuery({
    queryKey: [...paths.key, "variables"],
    queryFn: () => get<VariableList>(paths.variables),
  });
}

export interface Upsert {
  key: string;
  value?: string;
  visibility?: Visibility;
}

export function useSaveVariables(paths: EnvPaths) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      revision,
      upserts,
      deletes,
    }: {
      revision: number;
      upserts: Upsert[];
      deletes: string[];
    }) =>
      api<WriteResult>("PATCH", paths.variables, { upserts, deletes }, { "If-Match": `"${revision}"` }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: paths.key });
      qc.invalidateQueries({ queryKey: paths.listKey });
    },
  });
}

export function useReveal(paths: EnvPaths) {
  return useMutation({
    mutationFn: (keys: string[] | null) =>
      post<{ values: Record<string, string> }>(paths.reveal, { keys }),
  });
}

export function useImport(paths: EnvPaths) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      content: string;
      visibility: Record<string, Visibility>;
      dry_run: boolean;
    }) => post<ImportResult>(paths.import, body),
    onSuccess: (result) => {
      if (!result.dry_run) {
        qc.invalidateQueries({ queryKey: paths.key });
        qc.invalidateQueries({ queryKey: paths.listKey });
      }
    },
  });
}

export async function downloadExport(paths: EnvPaths) {
  const { text, filename } = await getText(paths.export);
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename ?? ".env";
  a.click();
  URL.revokeObjectURL(url);
}
