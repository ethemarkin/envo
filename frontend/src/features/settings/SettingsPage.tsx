import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { del } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { User } from "../../lib/types";
import { ME_KEY, useAuthConfig, useLogout, useMe } from "../auth/useAuth";
import { AdminSection } from "./AdminSection";

export function SettingsPage() {
  const { data: me, isPending } = useMe();
  const { data: config } = useAuthConfig();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const logoutAll = useLogout(true);
  const unlink = useMutation({
    mutationFn: (provider: string) => del<User>(`/api/auth/identities/${provider}`),
    onSuccess: (user) => qc.setQueryData(ME_KEY, user),
  });

  if (isPending || !me) return <Spinner />;

  const googleLinked = me.providers.includes("google");
  const redirectError = params.get("error");

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold tracking-tight">Ayarlar</h1>

      <section className="card divide-y divide-zinc-100">
        <div className="px-5 py-4">
          <h2 className="text-sm font-semibold">Hesap</h2>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-zinc-500">E-posta</dt>
            <dd>{me.email}</dd>
            <dt className="text-zinc-500">Ad</dt>
            <dd>{me.name ?? "—"}</dd>
            <dt className="text-zinc-500">Parola</dt>
            <dd>{me.has_password ? "Belirlenmiş" : "Yok (yalnızca Google ile giriş)"}</dd>
          </dl>
        </div>

        <div className="space-y-3 px-5 py-4">
          <h2 className="text-sm font-semibold">Bağlı hesaplar</h2>
          {params.get("linked") === "google" && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              Google hesabınız bağlandı.
            </div>
          )}
          {(redirectError || unlink.error) && (
            <ErrorNote>{errorMessage(unlink.error ?? redirectError)}</ErrorNote>
          )}
          <div className="flex items-center justify-between text-sm">
            <span>Google</span>
            {googleLinked ? (
              <button
                type="button"
                className="btn-secondary py-1.5"
                disabled={unlink.isPending}
                onClick={() => unlink.mutate("google")}
              >
                Bağlantıyı kaldır
              </button>
            ) : config?.google_enabled ? (
              <a href="/api/auth/google/start?link=true" className="btn-secondary py-1.5">
                Google hesabını bağla
              </a>
            ) : (
              <span className="text-zinc-400">Sunucuda yapılandırılmamış</span>
            )}
          </div>
        </div>

        <div className="space-y-2 px-5 py-4">
          <h2 className="text-sm font-semibold">Oturumlar</h2>
          <p className="text-sm text-zinc-600">
            Tüm cihazlardaki oturumları kapatır. Açık erişim token'ları en geç 15 dakika içinde
            geçersiz olur.
          </p>
          <button
            type="button"
            className="btn-danger"
            disabled={logoutAll.isPending}
            onClick={() => logoutAll.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            Tüm oturumları kapat
          </button>
        </div>
      </section>

      {me.is_admin && <AdminSection myId={me.id} />}
    </div>
  );
}
