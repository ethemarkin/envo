import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { get } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { AuditEvent, AuditPage } from "../../lib/types";
import { formatTime } from "../environments/HistoryPanel";

const ACTION_LABELS: Record<string, string> = {
  "auth.signup": "Hesap oluşturdu",
  "auth.login": "Giriş yaptı",
  "auth.login_failed": "Başarısız giriş denemesi",
  "auth.cli_login_approved": "CLI girişini onayladı",
  "group.created": "Group oluşturdu",
  "group.updated": "Group'u düzenledi",
  "group.deleted": "Group'u sildi",
  "project.created": "Proje oluşturdu",
  "project.updated": "Projeyi düzenledi",
  "project.deleted": "Projeyi sildi",
  "environment.created": "Ortam oluşturdu",
  "environment.updated": "Ortamı düzenledi",
  "environment.deleted": "Ortamı sildi",
  "variables.updated": "Değişkenleri değiştirdi",
  "variables.revealed": "Gizli değerleri görüntüledi",
  "variables.exported": "Değerleri dışa aktardı",
  "member.added": "Üye ekledi",
  "member.invited": "Davet gönderdi",
  "member.invitation_revoked": "Daveti iptal etti",
  "member.invitation_accepted": "Daveti kabul etti",
  "member.role_changed": "Üye rolünü değiştirdi",
  "member.removed": "Üyeyi çıkardı",
  "member.left": "Üyelikten ayrıldı",
  "service_token.created": "Servis token'ı oluşturdu",
  "service_token.revoked": "Servis token'ını iptal etti",
  "admin.settings_updated": "Kurulum ayarlarını değiştirdi",
  "admin.user_updated": "Yönetici yetkisini değiştirdi",
  "admin.user_deleted": "Kullanıcıyı sildi",
  "admin.user_invited": "Kuruluma davet gönderdi",
  "admin.invitation_revoked": "Kurulum davetini iptal etti",
};

const FILTERS: { label: string; prefix: string }[] = [
  { label: "Tümü", prefix: "" },
  { label: "Değişkenler", prefix: "variables." },
  { label: "Üyelik", prefix: "member." },
  { label: "Token'lar", prefix: "service_token." },
];

/** A compact, human summary of the event's details (they never hold values). */
function summary(e: AuditEvent): string {
  const d = e.details;
  const list = (v: unknown) => (Array.isArray(v) ? v.join(", ") : "");
  switch (e.action) {
    case "variables.updated": {
      const parts = [
        list(d.created) && `+ ${list(d.created)}`,
        list(d.updated) && `~ ${list(d.updated)}`,
        list(d.deleted) && `− ${list(d.deleted)}`,
      ].filter(Boolean);
      return `${d.environment ?? ""} rev ${d.revision ?? "?"}: ${parts.join("  ")}`;
    }
    case "variables.revealed":
      return `${d.environment ?? ""}: ${list(d.keys)}`;
    case "variables.exported":
      return `${d.environment ?? ""} (${d.format}, ${d.count} değişken)`;
    case "member.role_changed":
      return `${d.from} → ${d.to}`;
    case "member.invited":
    case "member.invitation_revoked":
      return String(d.email ?? "");
    case "auth.login_failed":
      return String(d.email ?? "");
    case "auth.login":
      return String(d.method ?? "");
    case "service_token.created":
      return `${d.name} (${list(d.environments)}${d.can_write ? ", yazma" : ""})`;
    default:
      return typeof d.slug === "string" ? d.slug : typeof d.path === "string" ? d.path : "";
  }
}

export function AuditLog({ endpoint, title }: { endpoint: string; title: string }) {
  const [filter, setFilter] = useState("");
  const events = useInfiniteQuery({
    queryKey: ["audit", endpoint, filter],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: "50" });
      if (filter) params.set("action", filter);
      if (pageParam) params.set("before", pageParam);
      return get<AuditPage>(`${endpoint}?${params}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_before,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Değişiklik ve erişim olayları. Değişken değerleri, parolalar ve token'lar kaydedilmez.
        </p>
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtre">
        {FILTERS.map((f) => (
          <button
            key={f.label}
            type="button"
            aria-pressed={filter === f.prefix}
            onClick={() => setFilter(f.prefix)}
            className={`rounded-full px-3 py-1 text-xs ${
              filter === f.prefix ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {events.isPending ? (
        <Spinner />
      ) : events.error ? (
        <ErrorNote>{errorMessage(events.error)}</ErrorNote>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Zaman</th>
                  <th className="px-4 py-2.5 font-medium">Kim</th>
                  <th className="px-4 py-2.5 font-medium">Ne</th>
                  <th className="px-4 py-2.5 font-medium">Ayrıntı</th>
                  <th className="px-4 py-2.5 font-medium">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {events.data.pages.flatMap((p) => p.events).map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="whitespace-nowrap px-4 py-2.5 text-zinc-500">{formatTime(e.created_at)}</td>
                    <td className="whitespace-nowrap px-4 py-2.5">
                      {e.actor.label}
                      {e.actor.type === "token" && (
                        <span className="ml-1 rounded bg-zinc-100 px-1 text-[11px] text-zinc-600">token</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">{ACTION_LABELS[e.action] ?? e.action}</td>
                    <td className="max-w-md break-words px-4 py-2.5 font-mono text-xs text-zinc-600">
                      {summary(e)}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-zinc-500">{e.ip ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.data.pages[0]?.events.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-zinc-500">Kayıt yok.</p>
            )}
          </div>
          {events.hasNextPage && (
            <button
              type="button"
              className="btn-secondary"
              disabled={events.isFetchingNextPage}
              onClick={() => events.fetchNextPage()}
            >
              Daha eski kayıtlar
            </button>
          )}
        </>
      )}
    </div>
  );
}
