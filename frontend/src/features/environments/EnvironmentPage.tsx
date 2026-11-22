import { useState } from "react";
import { Link, useParams } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { ApiError } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { Variable, Visibility } from "../../lib/types";
import { useProject } from "../navigation/queries";
import { ImportPanel } from "./ImportPanel";
import {
  downloadExport,
  envPaths,
  type Upsert,
  useEnvironment,
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

export function EnvironmentPage() {
  const { projectId = "", envId = "" } = useParams();
  const paths = envPaths(projectId, envId);
  const project = useProject(projectId);
  const env = useEnvironment(paths, envId);
  const vars = useVariables(paths);
  const save = useSaveVariables(paths);
  const reveal = useReveal(paths);

  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [deleted, setDeleted] = useState<Set<string>>(new Set());
  const [newRows, setNewRows] = useState<NewRow[]>([]);
  const [importing, setImporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);

  if (vars.isPending || env.isPending || project.isPending) return <Spinner />;
  const loadError = vars.error ?? env.error ?? project.error;
  if (loadError || !vars.data) return <ErrorNote>{errorMessage(loadError)}</ErrorNote>;
  if (!env.data) return <ErrorNote>{errorMessage("environment_not_found")}</ErrorNote>;

  const { variables, revision, can_write: canWrite, can_read_secrets: canRead } = vars.data;
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
    <div className="space-y-6 pb-24">
      <div>
        <Link to={`/projects/${projectId}`} className="text-sm text-zinc-500 hover:text-zinc-900">
          ← {project.data?.path ?? "Proje"}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{env.data.name}</h1>
          <span className="font-mono text-sm text-zinc-500">--env {env.data.slug}</span>
          {env.data.protected && (
            <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
              Korumalı
            </span>
          )}
          <span className="text-xs text-zinc-400">revizyon {revision}</span>
        </div>
        {!canWrite && (
          <p className="mt-2 text-sm text-zinc-500">
            Bu ortamda yalnızca görüntüleme yetkiniz var
            {canRead ? "." : "; gizli değerler maskeli gösterilir."}
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {canWrite && (
          <button type="button" className="btn-secondary" onClick={() => setImporting((v) => !v)}>
            .env içe aktar
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
            .env indir
          </button>
        )}
        {canRead && hasSecrets && (
          <button
            type="button"
            className="btn-secondary"
            disabled={reveal.isPending}
            onClick={() => revealKeys(null)}
          >
            Tüm gizli değerleri göster
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
              <th className="w-1/3 px-4 py-2.5 font-medium">Anahtar</th>
              <th className="px-4 py-2.5 font-medium">Değer</th>
              <th className="w-px px-4 py-2.5 font-medium">Görünürlük</th>
              {canWrite && <th className="w-px px-4 py-2.5" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {variables.length === 0 && newRows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-zinc-500">
                  Bu ortamda henüz değişken yok.
                  {canWrite && " Aşağıdan ekleyin veya bir .env dosyası içe aktarın."}
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
                    placeholder="YENI_ANAHTAR"
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
                    placeholder="değer"
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
                    Kaldır
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
              + Değişken ekle
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
              <p className="flex-1 text-sm text-zinc-600">{dirtyCount} kaydedilmemiş değişiklik</p>
            )}
            {conflict && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  discard();
                  vars.refetch();
                }}
              >
                Güncel hâli yükle
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={discard}>
              Vazgeç
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={save.isPending || dirtyCount === 0}
              onClick={submit}
            >
              {save.isPending ? "Kaydediliyor…" : "Kaydet"}
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
              title={isSecretHidden ? "Değiştirmek için yeni değer yazın" : undefined}
              onChange={(value) => onEdit({ value })}
            />
            {isSecretHidden && edit?.value === undefined && canRead && (
              <button
                type="button"
                className="btn-secondary shrink-0 py-1 text-xs"
                disabled={revealing}
                onClick={onReveal}
              >
                Göster
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
                {isSecretHidden ? "Göster" : "Gizle"}
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
            {isDeleted ? "Geri al" : "Sil"}
          </button>
        </td>
      )}
    </tr>
  );
}
