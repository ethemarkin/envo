import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { get, patch } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { AdminUser } from "../../lib/types";

interface InstanceSettings {
  allow_root_creation: boolean;
}

/** Instance settings and administrator assignment; shown to admins only. */
export function AdminSection({ myId }: { myId: string }) {
  const qc = useQueryClient();
  const settings = useQuery({
    queryKey: ["admin", "settings"],
    queryFn: () => get<InstanceSettings>("/api/admin/settings"),
  });
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => get<AdminUser[]>("/api/admin/users"),
  });
  const saveSettings = useMutation({
    mutationFn: (body: Partial<InstanceSettings>) =>
      patch<InstanceSettings>("/api/admin/settings", body),
    onSuccess: (data) => {
      qc.setQueryData(["admin", "settings"], data);
      qc.invalidateQueries({ queryKey: ["tree"] });
    },
  });
  const setAdmin = useMutation({
    mutationFn: ({ id, is_admin }: { id: string; is_admin: boolean }) =>
      patch<AdminUser>(`/api/admin/users/${id}`, { is_admin }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Kurulum yönetimi</h2>
      <div className="card divide-y divide-zinc-100">
        <div className="space-y-2 px-5 py-4">
          {settings.isPending ? (
            <Spinner />
          ) : settings.error ? (
            <ErrorNote>{errorMessage(settings.error)}</ErrorNote>
          ) : (
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-4"
                checked={settings.data.allow_root_creation}
                disabled={saveSettings.isPending}
                onChange={(e) => saveSettings.mutate({ allow_root_creation: e.target.checked })}
              />
              <span>
                <span className="font-medium">Herkes en üst seviyede group ve proje oluşturabilir</span>
                <span className="block text-zinc-500">
                  Kapalıyken yalnızca yöneticiler en üst seviyede oluşturabilir; diğer kullanıcılar
                  yetkili oldukları group'ların içinde çalışır.
                </span>
              </span>
            </label>
          )}
          {saveSettings.error && <ErrorNote>{errorMessage(saveSettings.error)}</ErrorNote>}
        </div>

        <div className="space-y-3 px-5 py-4">
          <h3 className="text-sm font-semibold">Kullanıcılar</h3>
          {setAdmin.error && <ErrorNote>{errorMessage(setAdmin.error)}</ErrorNote>}
          {users.isPending ? (
            <Spinner />
          ) : users.error ? (
            <ErrorNote>{errorMessage(users.error)}</ErrorNote>
          ) : (
            <ul className="divide-y divide-zinc-100 text-sm">
              {users.data.map((u) => (
                <li key={u.id} className="flex items-center gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate">
                      {u.name ?? u.email}
                      {u.id === myId && <span className="ml-1.5 text-xs text-zinc-500">(siz)</span>}
                    </p>
                    {u.name && <p className="truncate text-xs text-zinc-500">{u.email}</p>}
                  </div>
                  {u.is_admin && (
                    <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-xs text-white">
                      Yönetici
                    </span>
                  )}
                  <button
                    type="button"
                    className="btn-secondary py-1 text-xs"
                    disabled={setAdmin.isPending}
                    onClick={() => setAdmin.mutate({ id: u.id, is_admin: !u.is_admin })}
                  >
                    {u.is_admin ? "Yöneticilikten çıkar" : "Yönetici yap"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
