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
      post<Pick<InvitationPreview, "target_type" | "target_id">>(
        `/api/invitations/${encodeURIComponent(token)}/accept`,
      ),
    onSuccess: (r) => {
      qc.invalidateQueries();
      navigate(targetPath(r), { replace: true });
    },
  });

  if (preview.isPending || mePending) return <Spinner />;
  if (preview.error) {
    return (
      <AuthLayout title="Invitation">
        <ErrorNote>{errorMessage(preview.error)}</ErrorNote>
        <Link to="/" className="btn-secondary mt-4 w-full">
          Go to Envo
        </Link>
      </AuthLayout>
    );
  }

  const inv = preview.data;
  const here = `/invite/${token}`;
  const instance = inv.target_type === "instance";

  return (
    <AuthLayout title="Envo invitation">
      <div className="space-y-4 text-sm">
        {instance ? (
          <p>
            {inv.invited_by ? <strong>{inv.invited_by}</strong> : "An admin"} invited you to
            Envo.
          </p>
        ) : (
          <p>
            {inv.invited_by ? <strong>{inv.invited_by}</strong> : "A user"} invited you to the{" "}
            {inv.target_type === "group" ? "group" : "project"} <strong>{inv.target_name}</strong>{" "}
            with the <strong>{inv.role ? ROLE_LABELS[inv.role] : ""}</strong> role.
          </p>
        )}
        <dl className="grid grid-cols-[5.5rem_1fr] gap-y-1.5 rounded-md bg-zinc-50 p-3">
          {!instance && (
            <>
              <dt className="text-zinc-500">Path</dt>
              <dd className="font-mono text-xs leading-5">{inv.target_path}</dd>
            </>
          )}
          <dt className="text-zinc-500">Email</dt>
          <dd>{inv.email}</dd>
        </dl>

        {accept.error && <ErrorNote>{errorMessage(accept.error)}</ErrorNote>}

        {!me ? (
          <div className="space-y-2">
            <p className="text-zinc-600">
              To accept, sign in or create an account with <strong>{inv.email}</strong>.
            </p>
            <Link
              to="/register"
              state={{ from: here, email: inv.email, inviteToken: token, next: targetPath(inv) }}
              className="btn-primary w-full"
            >
              Create account
            </Link>
            <Link to="/login" state={{ from: here, email: inv.email }} className="btn-secondary w-full">
              Sign in
            </Link>
          </div>
        ) : me.email !== inv.email ? (
          <div className="space-y-2">
            <ErrorNote>
              You are signed in as <strong>{me.email}</strong>. This invitation was sent to{" "}
              <strong>{inv.email}</strong>.
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
              Sign out and use the right account
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="btn-primary w-full"
            disabled={accept.isPending}
            onClick={() => accept.mutate()}
          >
            Accept invitation
          </button>
        )}
      </div>
    </AuthLayout>
  );
}

function targetPath(t: Pick<InvitationPreview, "target_type" | "target_id">): string {
  if (t.target_type === "group") return `/groups/${t.target_id}`;
  if (t.target_type === "project") return `/projects/${t.target_id}`;
  return "/";
}
