import { type FormEvent, useState } from "react";
import { ErrorNote } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { type EnvPaths, useFolderMutations } from "./queries";

/** Tree order: parents before children, siblings by name. */
function compareTree(a: string, b: string): number {
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

type Mode = { kind: "create"; value: string } | { kind: "move"; value: string } | null;

/**
 * The project's folder tree. The structure is shared by every environment;
 * each folder has its own .env per environment. `counts` are this
 * environment's variables per folder.
 */
export function FolderTree({
  paths,
  folders,
  counts,
  selected,
  canManage,
  onSelect,
}: {
  paths: EnvPaths;
  folders: string[];
  counts: Record<string, number>;
  selected: string;
  canManage: boolean;
  onSelect: (path: string) => void;
}) {
  const { create, move, remove } = useFolderMutations(paths);
  const [mode, setMode] = useState<Mode>(null);
  const all = [...new Set(["", ...folders, ...Object.keys(counts)])].sort(compareTree);
  const busy = create.isPending || move.isPending || remove.isPending;
  const error = create.error ?? move.error ?? remove.error;

  function reset() {
    create.reset();
    move.reset();
    remove.reset();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!mode) return;
    const target = cleanPath(mode.value);
    if (mode.kind === "create") {
      create.mutate(target, {
        onSuccess: () => {
          setMode(null);
          onSelect(target);
        },
      });
    } else if (target === selected) {
      setMode(null);
    } else {
      move.mutate(
        { path: selected, new_path: target },
        {
          onSuccess: () => {
            setMode(null);
            onSelect(target);
          },
        },
      );
    }
  }

  function deleteSelected() {
    const subfolders = all.filter((p) => p.startsWith(`${selected}/`)).length;
    const what = subfolders > 0 ? `“${selected}” ve ${subfolders} alt klasörü` : `“${selected}”`;
    if (
      !window.confirm(
        `${what} silinsin mi?\n\nBu klasörlerin .env dosyaları TÜM ortamlarda silinir. ` +
          "Değerler her ortamın geçmişinde kalır ve geri alma ile döndürülebilir.",
      )
    ) {
      return;
    }
    remove.mutate(selected, { onSuccess: () => onSelect("") });
  }

  return (
    <nav aria-label="Klasörler" className="card overflow-hidden">
      <div className="border-b border-zinc-100 px-3 py-2.5">
        <p className="text-sm font-semibold">Klasörler</p>
        <p className="text-xs text-zinc-500">Yapı tüm ortamlarda ortaktır.</p>
      </div>
      <ul className="max-h-[60vh] overflow-y-auto py-1">
        {all.map((path) => {
          const depth = path ? path.split("/").length : 0;
          const name = path ? path.slice(path.lastIndexOf("/") + 1) : "/ (kök)";
          const count = counts[path] ?? 0;
          const active = path === selected;
          return (
            <li key={path || "/"}>
              <button
                type="button"
                aria-current={active ? "true" : undefined}
                title={path ? `${path}/.env` : ".env"}
                onClick={() => {
                  setMode(null);
                  reset();
                  onSelect(path);
                }}
                className={`flex w-full items-center gap-2 py-1.5 pr-3 text-left text-sm ${
                  active ? "bg-zinc-900 text-white" : "text-zinc-700 hover:bg-zinc-100"
                }`}
                style={{ paddingLeft: `${0.75 + depth * 0.9}rem` }}
              >
                <FolderIcon open={active} />
                <span className={`min-w-0 flex-1 truncate ${path ? "font-mono text-xs" : ""}`}>
                  {name}
                </span>
                <span
                  className={`rounded-full px-1.5 text-[11px] tabular-nums ${
                    active ? "bg-white/20" : count ? "bg-zinc-100 text-zinc-600" : "text-zinc-300"
                  }`}
                  title="Bu ortamdaki değişken sayısı"
                >
                  {count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {canManage && (
        <div className="space-y-2 border-t border-zinc-100 p-3">
          {mode ? (
            <form onSubmit={submit} className="space-y-2">
              <label className="label text-xs" htmlFor="folder-path">
                {mode.kind === "create" ? "Yeni klasör yolu" : `“${selected}” için yeni yol`}
              </label>
              <input
                id="folder-path"
                className="input font-mono text-xs"
                placeholder="services/api"
                autoFocus
                value={mode.value}
                onChange={(e) => setMode({ ...mode, value: e.target.value })}
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  className="btn-primary py-1 text-xs"
                  disabled={busy || !cleanPath(mode.value)}
                >
                  {mode.kind === "create" ? "Ekle" : "Taşı"}
                </button>
                <button
                  type="button"
                  className="btn-secondary py-1 text-xs"
                  onClick={() => {
                    setMode(null);
                    reset();
                  }}
                >
                  Vazgeç
                </button>
              </div>
              {mode.kind === "move" && (
                <p className="text-xs text-zinc-500">
                  Alt klasörler ve tüm ortamlardaki .env dosyaları da taşınır.
                </p>
              )}
            </form>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                className="btn-secondary py-1 text-xs"
                onClick={() => {
                  reset();
                  setMode({ kind: "create", value: selected ? `${selected}/` : "" });
                }}
              >
                + Klasör
              </button>
              {selected && (
                <>
                  <button
                    type="button"
                    className="btn-secondary py-1 text-xs"
                    onClick={() => {
                      reset();
                      setMode({ kind: "move", value: selected });
                    }}
                  >
                    Taşı / adlandır
                  </button>
                  <button
                    type="button"
                    className="btn-danger py-1 text-xs"
                    disabled={busy}
                    onClick={deleteSelected}
                  >
                    Sil
                  </button>
                </>
              )}
            </div>
          )}
          {error && <ErrorNote>{errorMessage(error)}</ErrorNote>}
        </div>
      )}
    </nav>
  );
}

function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5 shrink-0 opacity-70" aria-hidden="true">
      <path
        fill="currentColor"
        d={
          open
            ? "M1.5 3A1.5 1.5 0 0 1 3 1.5h3l1.5 1.5H13A1.5 1.5 0 0 1 14.5 4.5V5H3.6a1.5 1.5 0 0 0-1.43 1.05L1.5 8.2V3Zm.9 4.33A1 1 0 0 1 3.36 6.5H15a.5.5 0 0 1 .48.64l-1.6 5.5a1.5 1.5 0 0 1-1.44 1.08H2.5a1 1 0 0 1-.96-1.28l.86-5.11Z"
            : "M1.5 3.5A1.5 1.5 0 0 1 3 2h3l1.5 1.5H13A1.5 1.5 0 0 1 14.5 5v7A1.5 1.5 0 0 1 13 13.5H3A1.5 1.5 0 0 1 1.5 12V3.5Z"
        }
      />
    </svg>
  );
}
