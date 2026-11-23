import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { ErrorNote } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { AuthLayout, safeRedirect } from "./AuthLayout";
import { useLogin, useMe, useRegistration } from "./useAuth";

export function LoginPage() {
  const { data: me } = useMe();
  const login = useLogin();
  const registration = useRegistration();
  const navigate = useNavigate();
  const location = useLocation();
  const from = safeRedirect(location.state);
  const invitedEmail = (location.state as { email?: string } | null)?.email ?? "";
  const [email, setEmail] = useState(invitedEmail);
  const [password, setPassword] = useState("");

  if (me) return <Navigate to={from} replace />;


  function submit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ email, password }, { onSuccess: () => navigate(from, { replace: true }) });
  }

  return (
    <AuthLayout title="Sign in to Envo">
      <form onSubmit={submit} className="space-y-4">
        {login.error && (
          <ErrorNote>{errorMessage(login.error)}</ErrorNote>
        )}
        <div>
          <label htmlFor="email" className="label">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="password" className="label">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>
      </form>
      {registration.data && !registration.data.invitation_required ? (
        <p className="mt-5 text-center text-sm text-zinc-600">
          Don't have an account?{" "}
          <Link to="/register" state={{ from, email: invitedEmail }} className="font-medium text-zinc-900 underline-offset-2 hover:underline">
            Create account
          </Link>
        </p>
      ) : (
        <p className="mt-5 text-center text-sm text-zinc-500">
          Accounts can only be created by invitation. Use the link in your invitation email.
        </p>
      )}
    </AuthLayout>
  );
}
