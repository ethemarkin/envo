import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { get, post } from "../../lib/api";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import type { InvitationPreview } from "../../lib/types";
import { AuthLayout } from "../auth/AuthLayout";
import { useLogout, useMe } from "../auth/useAuth";

/** Landing page of the link in an invitation e-mail. */
export function InvitePage() {
  const { token = "" } = useParams();
  const { data: me, isPending: mePending } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const logout = useLogout();
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => get<InvitationPreview>(`/api/invitations/${encodeURIComponent(token)}`),
    retry: false,
  });
  const accept = useMutation({
    mutationFn: () =>
      post<{ target_type: "group" | "project"; target_id: string }>(
        `/api/invitations/${encodeURIComponent(token)}/accept`,
      ),
    onSuccess: (r) => {
      qc.invalidateQueries();
      navigate(r.target_type === "group" ? `/groups/${r.target_id}` : `/projects/${r.target_id}`, {
        replace: true,
      });
    },
  });

  if (preview.isPending || mePending) return <Spinner />;
  if (preview.error) {
    return (
      <AuthLayout title="Davet">
        <ErrorNote>{errorMessage(preview.error)}</ErrorNote>
        <Link to="/" className="btn-secondary mt-4 w-full">
          Envo'ya git
        </Link>
      </AuthLayout>
    );
  }

  const inv = preview.data;
  const here = `/invite/${token}`;
  const kind = inv.target_type === "group" ? "group" : "proje";

  return (
    <AuthLayout title="Envo daveti">
      <div className="space-y-4 text-sm">
        <p>
          {inv.invited_by ? <strong>{inv.invited_by}</strong> : "Bir kullanıcı"} sizi{" "}
          <strong>{inv.target_name}</strong> {kind === "group" ? "group'una" : "projesine"}{" "}
          <strong>{ROLE_LABELS[inv.role]}</strong> rolüyle davet etti.
        </p>
        <dl className="grid grid-cols-[5.5rem_1fr] gap-y-1.5 rounded-md bg-zinc-50 p-3">
          <dt className="text-zinc-500">Yol</dt>
          <dd className="font-mono text-xs leading-5">{inv.target_path}</dd>
          <dt className="text-zinc-500">E-posta</dt>
          <dd>{inv.email}</dd>
        </dl>

        {accept.error && <ErrorNote>{errorMessage(accept.error)}</ErrorNote>}

        {!me ? (
          <div className="space-y-2">
            <p className="text-zinc-600">
              Kabul etmek için <strong>{inv.email}</strong> adresiyle giriş yapın veya hesap oluşturun.
            </p>
            <Link to="/register" state={{ from: here, email: inv.email }} className="btn-primary w-full">
              Hesap oluştur
            </Link>
            <Link to="/login" state={{ from: here, email: inv.email }} className="btn-secondary w-full">
              Giriş yap
            </Link>
          </div>
        ) : me.email !== inv.email ? (
          <div className="space-y-2">
            <ErrorNote>
              Şu an <strong>{me.email}</strong> olarak giriş yaptınız. Bu davet{" "}
              <strong>{inv.email}</strong> adresine gönderildi.
            </ErrorNote>
            <button
              type="button"
              className="btn-secondary w-full"
              disabled={logout.isPending}
              onClick={() =>
                logout.mutate(undefined, {
                  onSettled: () => navigate("/login", { state: { from: here, email: inv.email } }),
                })
              }
            >
              Çıkış yapıp doğru hesapla gir
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="btn-primary w-full"
            disabled={accept.isPending}
            onClick={() => accept.mutate()}
          >
            Daveti kabul et
          </button>
        )}
      </div>
    </AuthLayout>
  );
}
