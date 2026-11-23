import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, del, get, getText, patch, post } from "../../lib/api";
import type {
  Environment,
  FolderChange,
  FolderList,
  ImportResult,
  VariableList,
  Visibility,
  WriteResult,
} from "../../lib/types";

/**
 * API paths of one environment, with the folder ("" = project root) whose
 * .env the per-folder endpoints address.
 */
export function envPaths(projectId: string, envId: string, folder = "") {
  const project = `/api/projects/${projectId}`;
  const base = `${project}/environments/${envId}`;
  const q = folder ? `?path=${encodeURIComponent(folder)}` : "";
  return {
    folder,
    environments: `${project}/environments`,
    folders: `${project}/folders`,
    /** Every folder's variables (listing). */
    variables: `${base}/variables`,
    /** Writes to this folder's variables. */
    folderVariables: `${base}/variables${q}`,
    reveal: `${base}/variables/reveal${q}`,
    import: `${base}/import${q}`,
    export: `${base}/export${q}`,
    revisions: `${base}/revisions`,
    key: ["projects", projectId, "environments", envId] as const,
    listKey: ["projects", projectId, "environments"] as const,
    foldersKey: ["projects", projectId, "folders"] as const,
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

function useInvalidateEnv(paths: EnvPaths) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: paths.key });
    qc.invalidateQueries({ queryKey: paths.listKey });
    qc.invalidateQueries({ queryKey: paths.foldersKey });
  };
}

export interface Upsert {
  key: string;
  value?: string;
  visibility?: Visibility;
}

export function useSaveVariables(paths: EnvPaths) {
  const invalidate = useInvalidateEnv(paths);
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
      api<WriteResult>(
        "PATCH",
        paths.folderVariables,
        { upserts, deletes },
        { "If-Match": `"${revision}"` },
      ),
    onSuccess: invalidate,
  });
}

export function useReveal(paths: EnvPaths) {
  return useMutation({
    mutationFn: (keys: string[] | null) =>
      post<{ values: Record<string, string> }>(paths.reveal, { keys }),
  });
}

export function useImport(paths: EnvPaths) {
  const invalidate = useInvalidateEnv(paths);
  return useMutation({
    mutationFn: (body: {
      content: string;
      visibility: Record<string, Visibility>;
      dry_run: boolean;
    }) => post<ImportResult>(paths.import, body),
    onSuccess: (result) => {
      if (!result.dry_run) invalidate();
    },
  });
}

/** The folder's .env as text, with the environment revision it was read at. */
export function useDotenv(paths: EnvPaths, enabled: boolean) {
  return useQuery({
    queryKey: [...paths.key, "dotenv", paths.folder],
    queryFn: async () => {
      const { text, etag } = await getText(paths.export);
      return { text, revision: etag ?? "" };
    },
    enabled,
    // The editor holds its own draft; don't reload under the user's hands.
    refetchOnWindowFocus: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 0,
  });
}

/** Replace the folder's .env with `content` (keys not in it are deleted). */
export function useSaveDotenv(paths: EnvPaths) {
  const invalidate = useInvalidateEnv(paths);
  return useMutation({
    mutationFn: ({ content, revision }: { content: string; revision: string }) =>
      api<ImportResult>(
        "POST",
        paths.import,
        { content, replace: true, dry_run: false },
        revision ? { "If-Match": revision } : {},
      ),
    onSuccess: invalidate,
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

// --- Folders (shared by every environment of the project) ------------------

export function useFolders(paths: EnvPaths) {
  return useQuery({
    queryKey: paths.foldersKey,
    queryFn: () => get<FolderList>(paths.folders),
  });
}

export function useFolderMutations(paths: EnvPaths) {
  const qc = useQueryClient();
  const onSuccess = () => {
    qc.invalidateQueries({ queryKey: paths.foldersKey });
    // Moves and deletes rewrite variables in every environment (the prefix
    // covers each environment's queries).
    qc.invalidateQueries({ queryKey: paths.listKey });
  };
  return {
    create: useMutation({
      mutationFn: (path: string) => post<FolderChange>(paths.folders, { path }),
      onSuccess,
    }),
    move: useMutation({
      mutationFn: (body: { path: string; new_path: string }) =>
        patch<FolderChange>(paths.folders, body),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: (path: string) =>
        del<FolderChange>(`${paths.folders}?path=${encodeURIComponent(path)}`),
      onSuccess,
    }),
  };
}
