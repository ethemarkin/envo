import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { del, get, patch, post } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { AdminUser, InstanceInvitation, InstanceInviteResult } from "../../lib/types";
import { CopyField } from "../navigation/MembersPanel";

interface InstanceSettings {
  allow_root_creation: boolean;
}

/** Instance settings, users and sign-up invitations; shown to admins only. */
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
  const deleteUser = useMutation({
    mutationFn: (id: string) => del(`/api/admin/users/${id}`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Kurulum yönetimi</h2>
        <Link to="/admin/audit" className="text-sm text-zinc-600 underline-offset-2 hover:underline">
          Denetim kaydı →
        </Link>
      </div>
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
          {(setAdmin.error ?? deleteUser.error) && (
            <ErrorNote>{errorMessage(setAdmin.error ?? deleteUser.error)}</ErrorNote>
          )}
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
                  {u.id !== myId && (
                    <button
                      type="button"
                      className="btn-secondary py-1 text-xs text-red-700"
                      disabled={deleteUser.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `${u.email} hesabı silinsin mi? Tüm üyelikleri ve oturumları kaldırılır; bu işlem geri alınamaz.`,
                          )
                        )
                          deleteUser.mutate(u.id);
                      }}
                    >
                      Sil
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <InviteToInstance />
      </div>
    </section>
  );
}

/** Sign-up invitations that give access to nothing yet; groups and projects
 *  invite people to themselves from their member lists. */
function InviteToInstance() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const pending = useQuery({
    queryKey: ["admin", "invitations"],
    queryFn: () => get<InstanceInvitation[]>("/api/admin/invitations"),
  });
  const invite = useMutation({
    mutationFn: (address: string) =>
      post<InstanceInviteResult>("/api/admin/invitations", { email: address }),
    onSuccess: () => {
      setEmail("");
      qc.invalidateQueries({ queryKey: ["admin", "invitations"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => del(`/api/admin/invitations/${id}`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin", "invitations"] }),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    invite.mutate(email.trim());
  }

  const sent = invite.data;
  const error = invite.error ?? revoke.error ?? pending.error;

  return (
    <div className="space-y-3 px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold">Davetler</h3>
        <p className="text-xs text-zinc-500">
          Hesaplar yalnızca davetle açılır. Buradan davet edilen kişi hesap oluşturabilir ama
          henüz hiçbir group veya projeye erişemez; group ve projeler kendi üye listelerinden
          rolle davet gönderir.
        </p>
      </div>
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <input
          type="email"
          required
          placeholder="kullanici@ornek.com"
          className="input min-w-48 flex-1"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-label="Davet edilecek e-posta"
        />
        <button type="submit" className="btn-primary" disabled={invite.isPending || !email.trim()}>
          Davet gönder
        </button>
      </form>
      {sent && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          {sent.invite_url ? (
            <>
              <p>
                <strong>{sent.invitation.email}</strong> için davet oluşturuldu, ancak sunucuda
                e-posta yapılandırılmadığı için gönderilemedi. Bu bağlantıyı kendiniz iletin:
              </p>
              <CopyField value={sent.invite_url} />
            </>
          ) : (
            <p>
              <strong>{sent.invitation.email}</strong> adresine davet e-postası gönderildi.
            </p>
          )}
        </div>
      )}
      {error && <ErrorNote>{errorMessage(error)}</ErrorNote>}
      {pending.isPending ? (
        <Spinner />
      ) : (
        pending.data &&
        pending.data.length > 0 && (
          <ul className="divide-y divide-zinc-100 text-sm">
            {pending.data.map((i) => (
              <li key={i.id} className="flex items-center gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate">{i.email}</p>
                  <p className="truncate text-xs text-zinc-500">
                    Bekliyor · {new Date(i.expires_at).toLocaleDateString("tr-TR")} tarihine kadar
                    geçerli
                    {i.invited_by && ` · ${i.invited_by}`}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn-secondary py-1 text-xs"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate(i.id)}
                >
                  İptal et
                </button>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
