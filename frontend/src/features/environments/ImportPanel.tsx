import { type ChangeEvent, useState } from "react";
import { ErrorNote } from "../../app/ErrorNote";
import { ApiError } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { DotenvError, ImportItem, Visibility } from "../../lib/types";
import { type EnvPaths, useImport } from "./queries";
import { VisibilityBadge, VisibilityToggle } from "./VisibilityToggle";

const STATUS_LABELS: Record<ImportItem["status"], string> = {
  new: "Yeni",
  changed: "Değişecek",
  unchanged: "Aynı",
};

/**
 * Paste or upload a .env, preview the merge (dry run), choose visibility for
 * new keys, then apply. Keys missing from the file are never deleted.
 */
export function ImportPanel({ paths, onClose }: { paths: EnvPaths; onClose: () => void }) {
  const [content, setContent] = useState("");
  const [visibility, setVisibility] = useState<Record<string, Visibility>>({});
  const preview = useImport(paths);
  const apply = useImport(paths);

  const items = preview.data?.items;
  const parseErrors =
    preview.error instanceof ApiError && preview.error.code === "invalid_dotenv"
      ? (preview.error.data.errors as DotenvError[])
      : null;

  function runPreview(text = content) {
    apply.reset();
    preview.mutate({ content: text, visibility: {}, dry_run: true });
  }

  async function loadFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setContent(text);
    setVisibility({});
    runPreview(text);
    e.target.value = "";
  }

  const counts = items?.reduce(
    (acc, i) => ({ ...acc, [i.status]: acc[i.status] + 1 }),
    { new: 0, changed: 0, unchanged: 0 },
  );
  const nothingToDo = counts !== undefined && counts.new + counts.changed === 0;

  return (
    <section className="card space-y-4 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold">.env içe aktar</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Dosyadaki anahtarlar eklenir veya güncellenir; dosyada olmayan değişkenler silinmez.
            Var olan değişkenler görünürlüklerini korur.
          </p>
        </div>
        <button type="button" className="btn-secondary py-1.5" onClick={onClose}>
          Kapat
        </button>
      </div>

      <textarea
        className="input min-h-40 font-mono text-xs"
        spellCheck={false}
        placeholder={"DATABASE_URL=postgres://...\nAPI_KEY=..."}
        value={content}
        onChange={(e) => {
          setContent(e.target.value);
          preview.reset();
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-primary"
          disabled={!content.trim() || preview.isPending}
          onClick={() => runPreview()}
        >
          Önizle
        </button>
        <label className="btn-secondary cursor-pointer">
          Dosya seç
          <input type="file" accept=".env,text/plain,*" className="sr-only" onChange={loadFile} />
        </label>
      </div>

      {parseErrors ? (
        <ErrorNote>
          <p className="font-medium">{errorMessage(preview.error)}</p>
          <ul className="mt-1 list-disc pl-5">
            {parseErrors.map((e) => (
              <li key={`${e.line}-${e.code}`}>
                {e.line > 0 ? `Satır ${e.line}: ` : ""}
                {e.message}
              </li>
            ))}
          </ul>
        </ErrorNote>
      ) : (
        preview.error && <ErrorNote>{errorMessage(preview.error)}</ErrorNote>
      )}

      {apply.data && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          İçe aktarıldı. Ortam revizyonu: {apply.data.revision}.
        </p>
      )}

      {items && counts && !apply.data && (
        <div className="space-y-3">
          <p className="text-sm text-zinc-600">
            {counts.new} yeni, {counts.changed} değişecek, {counts.unchanged} aynı.
          </p>
          <div className="overflow-hidden rounded-md border border-zinc-200">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-zinc-100">
                {items.map((item) => (
                  <tr key={item.key}>
                    <td className="px-3 py-2 font-mono text-xs">{item.key}</td>
                    <td className="px-3 py-2 text-xs text-zinc-500">{STATUS_LABELS[item.status]}</td>
                    <td className="px-3 py-2 text-right">
                      {item.status === "new" ? (
                        <VisibilityToggle
                          value={visibility[item.key] ?? "secret"}
                          onChange={(v) => setVisibility((prev) => ({ ...prev, [item.key]: v }))}
                        />
                      ) : (
                        <VisibilityBadge value={item.visibility} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {apply.error && <ErrorNote>{errorMessage(apply.error)}</ErrorNote>}
          <button
            type="button"
            className="btn-primary"
            disabled={nothingToDo || apply.isPending}
            onClick={() => apply.mutate({ content, visibility, dry_run: false })}
          >
            {nothingToDo ? "Değişiklik yok" : "İçe aktar"}
          </button>
        </div>
      )}
    </section>
  );
}
