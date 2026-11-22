import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { ErrorNote } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { AuthLayout, Divider, GoogleButton, safeRedirect } from "./AuthLayout";
import { useAuthConfig, useMe, useSignup } from "./useAuth";

const MIN_PASSWORD = 10;

export function RegisterPage() {
  const { data: me } = useMe();
  const { data: config } = useAuthConfig();
  const signup = useSignup();
  const navigate = useNavigate();
  const location = useLocation();
  const from = safeRedirect(location.state);
  const invitedEmail = (location.state as { email?: string } | null)?.email ?? "";
  const [name, setName] = useState("");
  const [email, setEmail] = useState(invitedEmail);
  const [password, setPassword] = useState("");

  if (me) return <Navigate to={from} replace />;

  function submit(e: FormEvent) {
    e.preventDefault();
    signup.mutate(
      { email, password, name: name.trim() || undefined },
      { onSuccess: () => navigate(from, { replace: true }) },
    );
  }

  return (
    <AuthLayout title="Envo hesabı oluşturun">
      {config?.google_enabled && (
        <>
          <GoogleButton label="Google ile kaydol" />
          <Divider />
        </>
      )}
      <form onSubmit={submit} className="space-y-4">
        {signup.error && <ErrorNote>{errorMessage(signup.error)}</ErrorNote>}
        <div>
          <label htmlFor="name" className="label">
            Ad soyad <span className="font-normal text-zinc-400">(isteğe bağlı)</span>
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
            E-posta
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
            Parola
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
          <p className="mt-1.5 text-xs text-zinc-500">En az {MIN_PASSWORD} karakter.</p>
        </div>
        <button type="submit" className="btn-primary w-full" disabled={signup.isPending}>
          {signup.isPending ? "Hesap oluşturuluyor…" : "Kaydol"}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-zinc-600">
        Zaten hesabınız var mı?{" "}
        <Link to="/login" state={{ from, email: invitedEmail }} className="font-medium text-zinc-900 underline-offset-2 hover:underline">
          Giriş yapın
        </Link>
      </p>
    </AuthLayout>
  );
}
