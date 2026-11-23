import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { AuthLayout, safeRedirect } from "./AuthLayout";
import { MIN_PASSWORD, useMe, useRegistration, useSignup } from "./useAuth";

interface RegisterState {
  from?: string;
  email?: string;
  /** Link token of the invitation the visitor came from. */
  inviteToken?: string;
  /** Where the invitation leads; signing up with it accepts it. */
  next?: string;
}

/**
 * Accounts are created by invitation only: the invitation page sends its
 * token here. Only the first account of an empty instance signs up without one.
 */
export function RegisterPage() {
  const { data: me } = useMe();
  const registration = useRegistration();
  const signup = useSignup();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as RegisterState | null) ?? {};
  const from = safeRedirect(state);
  const inviteToken = typeof state.inviteToken === "string" ? state.inviteToken : undefined;
  const invitedEmail = state.email ?? "";
  // Signing up with an invitation accepts it, so go straight to its target.
  const after = inviteToken ? safeRedirect({ from: state.next }) : from;
  const [name, setName] = useState("");
  const [email, setEmail] = useState(invitedEmail);
  const [password, setPassword] = useState("");

  if (me) return <Navigate to={after} replace />;
  if (!inviteToken && registration.isPending) return <Spinner />;

  if (!inviteToken && registration.data?.invitation_required !== false) {
    return (
      <AuthLayout title="Sign-up is by invitation only">
        <p className="text-sm text-zinc-600">
          On this Envo instance, accounts can only be created by invitation. Ask an admin or your
          team for an invitation, then create your account with the link in the email you receive.
        </p>
        {registration.error && <ErrorNote>{errorMessage(registration.error)}</ErrorNote>}
        <Link to="/login" state={{ from }} className="btn-secondary mt-5 w-full">
          Sign in
        </Link>
      </AuthLayout>
    );
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    signup.mutate(
      { email, password, name: name.trim() || undefined, invite_token: inviteToken },
      { onSuccess: () => navigate(after, { replace: true }) },
    );
  }

  return (
    <AuthLayout title="Create an Envo account">
      <form onSubmit={submit} className="space-y-4">
        {signup.error && <ErrorNote>{errorMessage(signup.error)}</ErrorNote>}
        <div>
          <label htmlFor="name" className="label">
            Full name <span className="font-normal text-zinc-400">(optional)</span>
          </label>
          <input
            id="name"
            autoComplete="name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="email" className="label">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            readOnly={!!inviteToken}
            className={inviteToken ? "input bg-zinc-50 text-zinc-600" : "input"}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {inviteToken && (
            <p className="mt-1.5 text-xs text-zinc-500">The address the invitation was sent to.</p>
          )}
        </div>
        <div>
          <label htmlFor="password" className="label">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className="mt-1.5 text-xs text-zinc-500">At least {MIN_PASSWORD} characters.</p>
        </div>
        <button type="submit" className="btn-primary w-full" disabled={signup.isPending}>
          {signup.isPending ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-zinc-600">
        Already have an account?{" "}
        <Link to="/login" state={{ from, email: invitedEmail }} className="font-medium text-zinc-900 underline-offset-2 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
