import { type FormEvent, useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import type { ProjectFile } from "../../lib/types";
import { useFolderMutations, useFolders } from "../environments/queries";

/** Tree order: parents before children, siblings by name. */
export function compareTree(a: string, b: string): number {
  const x = a ? a.split("/") : [];
  const y = b ? b.split("/") : [];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const [p, q] = [x[i] ?? "", y[i] ?? ""];
    if (p !== q) return p < q ? -1 : 1;
  }
  return x.length - y.length;
}

function cleanPath(raw: string): string {
  return raw
    .trim()
    .replace(/\\/g, "/")
    .split("/")
    .filter((s) => s && s !== ".")
    .join("/");
}

/** A file's path in the project: "backend/application.properties". */
export function filePath(path: string, name: string): string {
  return path ? `${path}/${name}` : name;
}

export function envFileName(path: string): string {
  return filePath(path, ".env");
}

/** File names placed in each folder: .env first, then by name. */
export function filesByFolder(files: ProjectFile[]): Map<string, string[]> {
  const byFolder = new Map<string, string[]>();
  for (const f of files) byFolder.set(f.path, [...(byFolder.get(f.path) ?? []), f.name]);
  for (const names of byFolder.values()) {
    names.sort((a, b) => (a === ".env" ? -1 : b === ".env" ? 1 : a.localeCompare(b)));
  }
  return byFolder;
}

type Mode =
  | { kind: "create"; value: string; env: boolean }
  | { kind: "move"; value: string }
  | { kind: "file"; value: string }
  | null;

/**
 * The project's folders and the files placed in them: .env files and config
 * files such as application.properties. The structure is shared by every
 * environment; contents are edited on each environment's page.
 */
export function ProjectTree({ projectId }: { projectId: string }) {
  const folders = useFolders(projectId);
  const { create, move, remove, addEnv, removeEnv, addFile, removeFile } =
    useFolderMutations(projectId);
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<Mode>(null);
  const mutations = [create, move, remove, addEnv, removeEnv, addFile, removeFile];
  const busy = mutations.some((m) => m.isPending);
  const error = mutations.find((m) => m.error)?.error;

  if (folders.isPending) return <Spinner />;
  if (folders.error)
    return <ErrorNote>{errorMessage(folders.error)}</ErrorNote>;

  const byFolder = filesByFolder(folders.data.files);
  const envFiles = new Set(folders.data.env_files);
  const all = [...new Set(["", ...folders.data.folders, ...byFolder.keys()])].sort(
    compareTree,
  );
  const current = all.includes(selected) ? selected : "";
  const manage = folders.data.can_manage;

  function reset() {
    for (const m of mutations) m.reset();
  }

  function select(path: string) {
    setMode(null);
    reset();
    setSelected(path);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!mode) return;
    if (mode.kind === "file") {
      addFile.mutate(
        { path: current, name: mode.value.trim() },
        { onSuccess: () => setMode(null) },
      );
      return;
    }
    const target = cleanPath(mode.value);
    const done = { onSuccess: () => select(target) };
    if (mode.kind === "create")
      create.mutate({ path: target, env: mode.env }, done);
    else if (target === current) setMode(null);
    else move.mutate({ path: current, new_path: target }, done);
  }

  function deleteFolder() {
    const below = all.filter((p) => p.startsWith(`${current}/`)).length;
    const what =
      below > 0
        ? `“${current}” and its ${below} subfolder${below === 1 ? "" : "s"}`
        : `“${current}”`;
    const ok = window.confirm(
      `Delete ${what}?\n\nThe .env and config files inside will be deleted in ALL environments. ` +
        "The values stay in each environment's history and can be restored with a roll back.",
    );
    if (ok) remove.mutate(current, { onSuccess: () => select("") });
  }

  function removeFileAt(path: string, name: string) {
    const ok = window.confirm(
      `Remove ${filePath(path, name)}?\n\nIts contents will be deleted in ALL environments; ` +
        "the folder stays. The contents stay in each environment's history.",
    );
    if (!ok) return;
    if (name === ".env") removeEnv.mutate(path);
    else removeFile.mutate({ path, name });
  }

  return (
    <section className="space-y-3" aria-labelledby="tree-title">
      <div>
        <h2 id="tree-title" className="text-lg font-semibold">
          Folders and files
        </h2>
        <p className="text-sm text-zinc-600">
          .env files and config files (e.g. application.properties). The structure is the same in
          every environment. Open an environment to edit its contents.
        </p>
      </div>

      <div className="card overflow-hidden">
        <ul className="py-1" aria-label="Project tree">
          {all.map((path) => {
            const depth = path ? path.split("/").length : 0;
            const name = path
              ? path.slice(path.lastIndexOf("/") + 1)
              : "/ (root)";
            const active = manage && path === current;
            return (
              <li key={path || "/"}>
                <button
                  type="button"
                  disabled={!manage}
                  aria-current={active ? "true" : undefined}
                  onClick={() => select(path)}
                  className={`flex w-full items-center gap-2 py-1.5 pr-4 text-left text-sm disabled:cursor-default ${
                    active
                      ? "bg-zinc-900 text-white"
                      : "text-zinc-700 enabled:hover:bg-zinc-100"
                  }`}
                  style={{ paddingLeft: `${1 + depth * 1.1}rem` }}
                >
                  <FolderIcon />
                  <span className={path ? "font-mono text-xs" : ""}>
                    {name}
                  </span>
                </button>
                {(byFolder.get(path) ?? []).map((file) => (
                  <div
                    key={file}
                    className="group flex items-center gap-2 py-1 pr-4 text-sm text-zinc-700"
                    style={{ paddingLeft: `${1 + (depth + 1) * 1.1}rem` }}
                  >
                    <FileIcon />
                    <span className="font-mono text-xs">{file}</span>
                    {manage && (
                      <button
                        type="button"
                        className="ml-auto text-xs text-zinc-400 hover:text-red-600"
                        disabled={busy}
                        onClick={() => removeFileAt(path, file)}
                        aria-label={`Remove ${filePath(path, file)}`}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                ))}
              </li>
            );
          })}
        </ul>

        {manage && (
          <div className="space-y-2 border-t border-zinc-100 p-4">
            {mode ? (
              <form
                onSubmit={submit}
                className="flex flex-wrap items-end gap-2"
              >
                <div className="min-w-56 flex-1">
                  <label className="label text-xs" htmlFor="folder-path">
                    {mode.kind === "create"
                      ? "New folder path"
                      : mode.kind === "file"
                        ? `Config file name in ${current ? `“${current}”` : "the root"}`
                        : `New path for “${current}”`}
                  </label>
                  <input
                    id="folder-path"
                    className="input font-mono text-xs"
                    placeholder={
                      mode.kind === "file" ? "application.properties" : "services/api"
                    }
                    autoFocus
                    value={mode.value}
                    onChange={(e) =>
                      setMode({ ...mode, value: e.target.value })
                    }
                  />
                </div>
                {mode.kind === "create" && (
                  <label className="flex items-center gap-1.5 pb-2 text-sm text-zinc-700">
                    <input
                      type="checkbox"
                      checked={mode.env}
                      onChange={(e) =>
                        setMode({ ...mode, env: e.target.checked })
                      }
                    />
                    Add a .env inside
                  </label>
                )}
                <button
                  type="submit"
                  className="btn-primary text-xs"
                  disabled={busy || !cleanPath(mode.value)}
                >
                  {mode.kind === "move" ? "Move" : "Add"}
                </button>
                <button
                  type="button"
                  className="btn-secondary text-xs"
                  onClick={() => {
                    setMode(null);
                    reset();
                  }}
                >
                  Cancel
                </button>
                {mode.kind === "move" && (
                  <p className="w-full text-xs text-zinc-500">
                    Subfolders and their files in every environment move too.
                  </p>
                )}
                {mode.kind === "file" && (
                  <p className="w-full text-xs text-zinc-500">
                    Any text file that must not be committed, e.g. application.properties,
                    config.json or appsettings.Local.json. Its contents are kept encrypted,
                    separately for each environment.
                  </p>
                )}
              </form>
            ) : (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 font-mono text-xs text-zinc-500">
                  {current || "/"}
                </span>
                <button
                  type="button"
                  className="btn-secondary py-1 text-xs"
                  onClick={() => {
                    reset();
                    setMode({
                      kind: "create",
                      value: current ? `${current}/` : "",
                      env: true,
                    });
                  }}
                >
                  + Subfolder
                </button>
                {!envFiles.has(current) && (
                  <button
                    type="button"
                    className="btn-secondary py-1 text-xs"
                    disabled={busy}
                    onClick={() => addEnv.mutate(current)}
                  >
                    + .env
                  </button>
                )}
                <button
                  type="button"
                  className="btn-secondary py-1 text-xs"
                  onClick={() => {
                    reset();
                    setMode({ kind: "file", value: "" });
                  }}
                >
                  + Config file
                </button>
                {current && (
                  <>
                    <button
                      type="button"
                      className="btn-secondary py-1 text-xs"
                      onClick={() => {
                        reset();
                        setMode({ kind: "move", value: current });
                      }}
                    >
                      Move / rename
                    </button>
                    <button
                      type="button"
                      className="btn-danger py-1 text-xs"
                      disabled={busy}
                      onClick={deleteFolder}
                    >
                      Delete folder
                    </button>
                  </>
                )}
              </div>
            )}
            {error && <ErrorNote>{errorMessage(error)}</ErrorNote>}
          </div>
        )}
      </div>
    </section>
  );
}

function FolderIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="size-3.5 shrink-0 opacity-70"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M1.5 3.5A1.5 1.5 0 0 1 3 2h3l1.5 1.5H13A1.5 1.5 0 0 1 14.5 5v7A1.5 1.5 0 0 1 13 13.5H3A1.5 1.5 0 0 1 1.5 12V3.5Z"
      />
    </svg>
  );
}

export function FileIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="size-3.5 shrink-0 opacity-60"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M4 1.5h5.5L13 5v8.5A1 1 0 0 1 12 14.5H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Zm5 .9V5.5h3.1L9 2.4Z"
      />
    </svg>
  );
}
