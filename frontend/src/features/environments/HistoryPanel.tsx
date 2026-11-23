import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { api, get } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { Revision, RevisionPage, WriteResult } from "../../lib/types";
import type { EnvPaths } from "./queries";

const SOURCE_LABELS: Record<Revision["source"], string> = {
  web: "Web",
  cli: "CLI",
  token: "Servis token'ı",
  rollback: "Geri alma",
};

const ACTION_STYLE = {
  create: { sign: "+", className: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  update: { sign: "~", className: "bg-amber-50 text-amber-900 ring-amber-200" },
  delete: { sign: "−", className: "bg-red-50 text-red-800 ring-red-200" },
} as const;

/** Change-set messages written by the server, in Turkish. */
function describeMessage(message: string): string | null {
  if (message.startsWith("rollback to ")) return `revizyon ${message.slice(12)}`;
  if (message.startsWith("move ")) return `klasör taşındı: ${message.slice(5).replace(" -> ", " → ")}`;
  if (message.startsWith("delete ")) return `klasör silindi: ${message.slice(7)}`;
  if (message === "edit .env") return ".env düzenlendi";
  if (message === "import") return "içe aktarma";
  return null;
}

export function formatTime(value: string): string {
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

/**
 * Change sets of an environment (keys only, never values) with rollback.
 * A rollback applies the old state as a new revision; nothing is erased.
 */
export function HistoryPanel({ paths, canWrite }: { paths: EnvPaths; canWrite: boolean }) {
  const qc = useQueryClient();
  const base = paths.revisions;
  const history = useInfiniteQuery({
    queryKey: [...paths.key, "revisions"],
    queryFn: ({ pageParam }) =>
      get<RevisionPage>(`${base}?limit=20${pageParam ? `&before=${pageParam}` : ""}`),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_before,
  });
  const rollback = useMutation({
    mutationFn: ({ revision, current }: { revision: number; current: number }) =>
      api<WriteResult>("POST", `${base}/${revision}/rollback`, undefined, {
        "If-Match": `"${current}"`,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: paths.key });
      qc.invalidateQueries({ queryKey: paths.listKey });
    },
  });

  if (history.isPending) return <Spinner />;
  if (history.error) return <ErrorNote>{errorMessage(history.error)}</ErrorNote>;

  const current = history.data.pages[0]?.current_revision ?? 0;
  const revisions = history.data.pages.flatMap((p) => p.revisions);

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Geçmiş</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Her kayıt bir revizyon oluşturur. Geri almak eski durumu yeni bir revizyon olarak uygular;
          geçmiş silinmez. Değerler burada gösterilmez.
        </p>
      </div>
      {rollback.error && <ErrorNote>{errorMessage(rollback.error)}</ErrorNote>}
      {rollback.data && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Geri alındı: revizyon {rollback.data.revision} oluşturuldu ({rollback.data.created.length}{" "}
          eklendi, {rollback.data.updated.length} değişti, {rollback.data.deleted.length} silindi).
        </p>
      )}
      {revisions.length === 0 ? (
        <p className="text-sm text-zinc-500">Henüz değişiklik yok.</p>
      ) : (
        <ol className="card divide-y divide-zinc-100">
          {revisions.map((r) => (
            <li key={r.revision} className="flex flex-wrap items-start gap-3 px-4 py-3 text-sm">
              <span className="w-14 shrink-0 font-mono text-xs text-zinc-500">rev {r.revision}</span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-zinc-700">
                  <span className="font-medium">{r.actor.label}</span>
                  <span className="text-zinc-400"> · {formatTime(r.created_at)} · </span>
                  <span className="text-zinc-500">{SOURCE_LABELS[r.source]}</span>
                  {r.message && describeMessage(r.message) && (
                    <span className="text-zinc-500"> ({describeMessage(r.message)})</span>
                  )}
                </p>
                <div className="flex flex-wrap gap-1">
                  {r.changes.map((ch) => (
                    <span
                      key={`${ch.path}/${ch.key}`}
                      className={`rounded px-1.5 py-0.5 font-mono text-[11px] ring-1 ${ACTION_STYLE[ch.action].className}`}
                    >
                      {ACTION_STYLE[ch.action].sign} {ch.path ? `${ch.path}/` : ""}
                      {ch.key}
                    </span>
                  ))}
                </div>
              </div>
              {canWrite && r.revision !== current && (
                <button
                  type="button"
                  className="btn-secondary py-1 text-xs"
                  disabled={rollback.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Ortam revizyon ${r.revision} sonrasındaki hâline döndürülsün mü? Bu, yeni bir revizyon oluşturur.`,
                      )
                    ) {
                      rollback.mutate({ revision: r.revision, current });
                    }
                  }}
                >
                  Bu hâline dön
                </button>
              )}
              {r.revision === current && (
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">güncel</span>
              )}
            </li>
          ))}
        </ol>
      )}
      {history.hasNextPage && (
        <button
          type="button"
          className="btn-secondary"
          disabled={history.isFetchingNextPage}
          onClick={() => history.fetchNextPage()}
        >
          Daha eski revizyonlar
        </button>
      )}
    </section>
  );
}
