import { useCallback, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { ApiError } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { Variable, Visibility } from "../../lib/types";
import { useProject } from "../navigation/queries";
import { DotenvEditor } from "./DotenvEditor";
import { compareTree, envFileName, FileIcon } from "../projects/ProjectTree";
import { HistoryPanel } from "./HistoryPanel";
import { ImportPanel } from "./ImportPanel";
import {
  downloadExport,
  type EnvPaths,
  envPaths,
  type Upsert,
  useEnvironment,
  useFolders,
  useReveal,
  useSaveVariables,
  useVariables,
} from "./queries";
import { VisibilityToggle } from "./VisibilityToggle";

interface Edit {
  value?: string;
  visibility?: Visibility;
}

interface NewRow {
  id: number;
  key: string;
  value: string;
  visibility: Visibility;
}

const MASK = "••••••••••••";
let nextRowId = 1;

type View = "env" | "vars";

export function EnvironmentPage() {
  const { projectId = "", envId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const requested = search.get("path");
  const base = envPaths(projectId, envId);
  const project = useProject(projectId);
  const env = useEnvironment(base, envId);
  const vars = useVariables(base);
  const folders = useFolders(projectId);
  const [showHistory, setShowHistory] = useState(false);
  const [editorDirty, setEditorDirty] = useState(false);
  const onDirtyChange = useCallback((dirty: boolean) => setEditorDirty(dirty), []);

  if (vars.isPending || env.isPending || project.isPending || folders.isPending) {
    return <Spinner />;
  }
  const loadError = vars.error ?? env.error ?? project.error ?? folders.error;
  if (loadError || !vars.data || !folders.data) {
    return <ErrorNote>{errorMessage(loadError)}</ErrorNote>;
  }
  if (!env.data) return <ErrorNote>{errorMessage("environment_not_found")}</ErrorNote>;

  const { variables, revision, can_write: canWrite, can_read_secrets: canRead } = vars.data;
  const view: View = search.get("view") === "vars" || !canRead ? "vars" : "env";
  const counts: Record<string, number> = {};
  for (const v of variables) counts[v.path] = (counts[v.path] ?? 0) + 1;
  // The project decides where a .env lives; values elsewhere (if any) still show.
  const files = [...new Set([...folders.data.env_files, ...Object.keys(counts)])].sort(compareTree);
  const folder = requested ?? (files.includes("") ? "" : (files[0] ?? ""));
  const paths = envPaths(projectId, envId, folder);
  const projectLink = `/projects/${projectId}`;

  function navigate(next: { path?: string; view?: View }) {
    if (editorDirty && !window.confirm("Unsaved .env changes will be lost. Continue?")) {
      return;
    }
    setEditorDirty(false);
    const params = new URLSearchParams(search);
    const path = next.path ?? folder;
    const nextView = next.view ?? view;
    if (path) params.set("path", path);
    else params.delete("path");
    if (nextView === "vars") params.set("view", "vars");
    else params.delete("view");
    setSearch(params, { replace: true });
  }

  const fileName = envFileName(folder);
  const tab = (value: View, label: string, disabled = false) => (
    <button
      type="button"
      role="tab"
      aria-selected={view === value}
      disabled={disabled}
      onClick={() => navigate({ view: value })}
      className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40 ${
        view === value
          ? "border-zinc-900 text-zinc-900"
          : "border-transparent text-zinc-500 hover:text-zinc-800"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-6 pb-24">
      <div>
        <Link to={`/projects/${projectId}`} className="text-sm text-zinc-500 hover:text-zinc-900">
          ← {project.data?.path ?? "Project"}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{env.data.name}</h1>
          <span className="font-mono text-sm text-zinc-500">--env {env.data.slug}</span>
          {env.data.protected && (
            <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
              Protected
            </span>
          )}
          <span className="text-xs text-zinc-400">revision {revision}</span>
          <button
            type="button"
            className="btn-secondary ml-auto py-1.5"
            aria-pressed={showHistory}
            onClick={() => setShowHistory((v) => !v)}
          >
            {showHistory ? "Hide history" : "History"}
          </button>
        </div>
        {!canWrite && (
          <p className="mt-2 text-sm text-zinc-500">
            You have read-only access to this environment
            {canRead ? "." : "; secret values are masked."}
          </p>
        )}
      </div>

      {showHistory && <HistoryPanel paths={paths} canWrite={canWrite} />}

      {files.length === 0 ? (
        <div className="card px-6 py-10 text-center text-sm text-zinc-600">
          This project has no .env files yet.{" "}
          <Link to={projectLink} className="font-medium text-zinc-900 underline underline-offset-2">
            Go to the project page
          </Link>{" "}
          to add a .env to a folder or the root.
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <aside className="lg:sticky lg:top-4 lg:self-start">
            <EnvFileList
              files={files}
              counts={counts}
              selected={folder}
              projectLink={projectLink}
              onSelect={(path) => navigate({ path })}
            />
          </aside>

          <section className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-x-4 border-b border-zinc-200">
              <h2 className="pb-2 font-mono text-sm font-medium text-zinc-800">
                {fileName}
                {view === "env" && editorDirty && (
                  <span className="ml-2 font-sans text-xs font-normal text-amber-600">
                    ● unsaved
                  </span>
                )}
                {view === "env" && !canWrite && (
                  <span className="ml-2 font-sans text-xs font-normal text-zinc-500">read-only</span>
                )}
              </h2>
              <div role="tablist" className="flex">
                {tab("env", "Edit .env", !canRead)}
                {tab("vars", "Variables")}
              </div>
            </div>
            {view === "env" ? (
              <DotenvEditor
                key={`${envId}:${folder}`}
                paths={paths}
                canWrite={canWrite}
                onDirtyChange={onDirtyChange}
              />
            ) : (
              <FolderVariables
                key={`${envId}:${folder}`}
                paths={paths}
                variables={variables.filter((v) => v.path === folder)}
                revision={revision}
                canWrite={canWrite}
                canRead={canRead}
                onReload={() => vars.refetch()}
              />
            )}
          </section>
        </div>
      )}
    </div>
  );
}

/**
 * The .env files of the project, to pick which one to edit in this
 * environment. Where they live is managed on the project page.
 */
function EnvFileList({
  files,
  counts,
  selected,
  projectLink,
  onSelect,
}: {
  files: string[];
  counts: Record<string, number>;
  selected: string;
  projectLink: string;
  onSelect: (path: string) => void;
}) {
  return (
    <nav aria-label=".env files" className="card overflow-hidden">
      <div className="border-b border-zinc-100 px-3 py-2.5">
        <p className="text-sm font-semibold">.env files</p>
        <p className="text-xs text-zinc-500">
          Locations are managed on the{" "}
          <Link to={projectLink} className="underline underline-offset-2 hover:text-zinc-800">
            project page
          </Link>
          .
        </p>
      </div>
      <ul className="max-h-[60vh] overflow-y-auto py-1">
        {files.map((path) => {
          const active = path === selected;
          const count = counts[path] ?? 0;
          return (
            <li key={path || "/"}>
              <button
                type="button"
                aria-current={active ? "true" : undefined}
                onClick={() => onSelect(path)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm ${
                  active ? "bg-zinc-900 text-white" : "text-zinc-700 hover:bg-zinc-100"
                }`}
              >
                <FileIcon />
                <span className="min-w-0 flex-1 truncate font-mono text-xs">{envFileName(path)}</span>
                <span
                  className={`rounded-full px-1.5 text-[11px] tabular-nums ${
                    active ? "bg-white/20" : count ? "bg-zinc-100 text-zinc-600" : "text-zinc-300"
                  }`}
                  title="Number of variables in this environment"
                >
                  {count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** The folder's variables as an editable table (keys, values, visibility). */
function FolderVariables({
  paths,
  variables,
  revision,
  canWrite,
  canRead,
  onReload,
}: {
  paths: EnvPaths;
  variables: Variable[];
  revision: number;
  canWrite: boolean;
  canRead: boolean;
  onReload: () => void;
}) {
  const save = useSaveVariables(paths);
  const reveal = useReveal(paths);

  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [deleted, setDeleted] = useState<Set<string>>(new Set());
  const [newRows, setNewRows] = useState<NewRow[]>([]);
  const [importing, setImporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);

  const dirtyCount = Object.keys(edits).length + deleted.size + newRows.length;

  function discard() {
    setEdits({});
    setDeleted(new Set());
    setNewRows([]);
    save.reset();
  }

  function edit(key: string, patch: Edit) {
    const original = variables.find((v) => v.key === key);
    const originalValue = original?.visibility === "visible" ? original.value : revealed[key];
    setEdits((prev) => {
      const merged: Edit = { ...prev[key], ...patch };
      // Editing back to the original state is not a change.
      if (merged.visibility === original?.visibility) delete merged.visibility;
      if (merged.value !== undefined && merged.value === originalValue) delete merged.value;
      const { [key]: _, ...rest } = prev;
      return Object.keys(merged).length > 0 ? { ...rest, [key]: merged } : rest;
    });
  }

  function toggleDelete(key: string) {
    setDeleted((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function revealKeys(keys: string[] | null) {
    reveal.mutate(keys, { onSuccess: (r) => setRevealed((prev) => ({ ...prev, ...r.values })) });
  }

  function submit() {
    const upserts: Upsert[] = [
      ...Object.entries(edits)
        .filter(([key]) => !deleted.has(key))
        .map(([key, e]) => ({ key, value: e.value, visibility: e.visibility })),
      ...newRows.map((r) => ({ key: r.key.trim(), value: r.value, visibility: r.visibility })),
    ];
    save.mutate(
      { revision, upserts, deletes: [...deleted] },
      {
        onSuccess: () => {
          setEdits({});
          setDeleted(new Set());
          setNewRows([]);
          setRevealed({});
        },
      },
    );
  }

  const conflict = save.error instanceof ApiError && save.error.code === "revision_conflict";
  const hasSecrets = variables.some((v) => v.visibility === "secret");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {canWrite && (
          <button type="button" className="btn-secondary" onClick={() => setImporting((v) => !v)}>
            Import .env
          </button>
        )}
        {canRead && (
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setExportError(null);
              downloadExport(paths).catch(setExportError);
            }}
          >
            Download .env
          </button>
        )}
        {canRead && hasSecrets && (
          <button
            type="button"
            className="btn-secondary"
            disabled={reveal.isPending}
            onClick={() => revealKeys(null)}
          >
            Show all secret values
          </button>
        )}
      </div>

      {importing && <ImportPanel paths={paths} onClose={() => setImporting(false)} />}
      {exportError != null && <ErrorNote>{errorMessage(exportError)}</ErrorNote>}
      {reveal.error && <ErrorNote>{errorMessage(reveal.error)}</ErrorNote>}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="w-1/3 px-4 py-2.5 font-medium">Key</th>
              <th className="px-4 py-2.5 font-medium">Value</th>
              <th className="w-px px-4 py-2.5 font-medium">Visibility</th>
              {canWrite && <th className="w-px px-4 py-2.5" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {variables.length === 0 && newRows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-zinc-500">
                  This folder's .env is empty in this environment.
                  {canWrite && " Add variables below or import a .env file."}
                </td>
              </tr>
            )}
            {variables.map((v) => (
              <VariableRow
                key={v.key}
                variable={v}
                edit={edits[v.key]}
                revealedValue={revealed[v.key]}
                isDeleted={deleted.has(v.key)}
                canWrite={canWrite}
                canRead={canRead}
                revealing={reveal.isPending}
                onEdit={(patch) => edit(v.key, patch)}
                onReveal={() => revealKeys([v.key])}
                onHide={() =>
                  setRevealed((prev) => {
                    const { [v.key]: _, ...rest } = prev;
                    return rest;
                  })
                }
                onToggleDelete={() => toggleDelete(v.key)}
              />
            ))}
            {newRows.map((row) => (
              <tr key={row.id} className="bg-emerald-50/40">
                <td className="px-4 py-2 align-top">
                  <input
                    className="input font-mono text-xs"
                    placeholder="NEW_KEY"
                    value={row.key}
                    autoFocus
                    onChange={(e) =>
                      setNewRows((rows) =>
                        rows.map((r) => (r.id === row.id ? { ...r, key: e.target.value } : r)),
                      )
                    }
                  />
                </td>
                <td className="px-4 py-2 align-top">
                  <ValueInput
                    value={row.value}
                    placeholder="value"
                    onChange={(value) =>
                      setNewRows((rows) => rows.map((r) => (r.id === row.id ? { ...r, value } : r)))
                    }
                  />
                </td>
                <td className="px-4 py-2 align-top">
                  <VisibilityToggle
                    value={row.visibility}
                    onChange={(visibility) =>
                      setNewRows((rows) =>
                        rows.map((r) => (r.id === row.id ? { ...r, visibility } : r)),
                      )
                    }
                  />
                </td>
                <td className="px-4 py-2 align-top">
                  <button
                    type="button"
                    className="btn-secondary py-1 text-xs"
                    onClick={() => setNewRows((rows) => rows.filter((r) => r.id !== row.id))}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {canWrite && (
          <div className="border-t border-zinc-100 px-4 py-3">
            <button
              type="button"
              className="btn-secondary py-1.5"
              onClick={() =>
                setNewRows((rows) => [
                  ...rows,
                  { id: nextRowId++, key: "", value: "", visibility: "secret" },
                ])
              }
            >
              + Add variable
            </button>
          </div>
        )}
      </div>

      {canWrite && (dirtyCount > 0 || save.error) && (
        <div className="fixed inset-x-0 bottom-0 border-t border-zinc-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-3">
            {save.error ? (
              <p className="flex-1 text-sm text-red-700">{errorMessage(save.error)}</p>
            ) : (
              <p className="flex-1 text-sm text-zinc-600">{dirtyCount} unsaved {dirtyCount === 1 ? "change" : "changes"}</p>
            )}
            {conflict && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  discard();
                  onReload();
                }}
              >
                Load latest version
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={discard}>
              Discard
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={save.isPending || dirtyCount === 0}
              onClick={submit}
            >
              {save.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ValueInput({
  value,
  placeholder,
  title,
  disabled,
  onChange,
}: {
  value: string;
  placeholder?: string;
  title?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const lines = Math.min(value.split("\n").length, 8);
  return (
    <textarea
      className="input resize-y font-mono text-xs"
      rows={lines}
      spellCheck={false}
      autoComplete="off"
      placeholder={placeholder}
      title={title}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function VariableRow({
  variable: v,
  edit,
  revealedValue,
  isDeleted,
  canWrite,
  canRead,
  revealing,
  onEdit,
  onReveal,
  onHide,
  onToggleDelete,
}: {
  variable: Variable;
  edit: Edit | undefined;
  revealedValue: string | undefined;
  isDeleted: boolean;
  canWrite: boolean;
  canRead: boolean;
  revealing: boolean;
  onEdit: (patch: Edit) => void;
  onReveal: () => void;
  onHide: () => void;
  onToggleDelete: () => void;
}) {
  const visibility = edit?.visibility ?? v.visibility;
  const known = v.visibility === "visible" ? v.value : revealedValue;
  const shown = edit?.value ?? known;
  const isSecretHidden = v.visibility === "secret" && revealedValue === undefined;

  return (
    <tr className={isDeleted ? "bg-red-50/50" : edit ? "bg-amber-50/40" : undefined}>
      <td className="px-4 py-2 align-top">
        <span className={`font-mono text-xs ${isDeleted ? "text-zinc-400 line-through" : ""}`}>
          {v.key}
        </span>
      </td>
      <td className="px-4 py-2 align-top">
        {canWrite && !isDeleted ? (
          <div className="flex items-start gap-2">
            <ValueInput
              value={shown ?? ""}
              placeholder={isSecretHidden ? MASK : ""}
              title={isSecretHidden ? "Type a new value to change it" : undefined}
              onChange={(value) => onEdit({ value })}
            />
            {isSecretHidden && edit?.value === undefined && canRead && (
              <button
                type="button"
                className="btn-secondary shrink-0 py-1 text-xs"
                disabled={revealing}
                onClick={onReveal}
              >
                Show
              </button>
            )}
          </div>
        ) : (
          <div className="flex items-start gap-2">
            <code
              className={`block min-w-0 flex-1 whitespace-pre-wrap break-all font-mono text-xs ${
                isDeleted ? "text-zinc-400 line-through" : ""
              }`}
            >
              {isSecretHidden ? MASK : (known ?? "")}
            </code>
            {v.visibility === "secret" && canRead && !isDeleted && (
              <button
                type="button"
                className="btn-secondary shrink-0 py-1 text-xs"
                disabled={revealing}
                onClick={isSecretHidden ? onReveal : onHide}
              >
                {isSecretHidden ? "Show" : "Hide"}
              </button>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-2 align-top">
        <VisibilityToggle
          value={visibility}
          disabled={!canWrite || isDeleted}
          onChange={(next) => onEdit({ visibility: next })}
        />
      </td>
      {canWrite && (
        <td className="px-4 py-2 align-top">
          <button
            type="button"
            className={`${isDeleted ? "btn-secondary" : "btn-danger"} py-1 text-xs`}
            onClick={onToggleDelete}
          >
            {isDeleted ? "Undo" : "Delete"}
          </button>
        </td>
      )}
    </tr>
  );
}
