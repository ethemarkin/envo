import { useNavigate } from "react-router";
import { Spinner } from "../../app/ErrorNote";
import { useLogout, useMe } from "../auth/useAuth";
import { AdminSection } from "./AdminSection";
import { PasswordSection } from "./PasswordSection";

export function SettingsPage() {
  const { data: me, isPending } = useMe();
  const navigate = useNavigate();
  const logoutAll = useLogout(true);

  if (isPending || !me) return <Spinner />;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>

      <section className="card divide-y divide-zinc-100">
        <div className="px-5 py-4">
          <h2 className="text-sm font-semibold">Account</h2>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-zinc-500">Email</dt>
            <dd>{me.email}</dd>
            <dt className="text-zinc-500">Name</dt>
            <dd>{me.name ?? "—"}</dd>
          </dl>
        </div>

        <PasswordSection />

        <div className="space-y-2 px-5 py-4">
          <h2 className="text-sm font-semibold">Sessions</h2>
          <p className="text-sm text-zinc-600">
            Signs you out on all devices. Access tokens already issued expire within 15 minutes.
          </p>
          <button
            type="button"
            className="btn-danger"
            disabled={logoutAll.isPending}
            onClick={() => logoutAll.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            Sign out of all sessions
          </button>
        </div>
      </section>

      {me.is_admin && <AdminSection myId={me.id} />}
    </div>
  );
}
