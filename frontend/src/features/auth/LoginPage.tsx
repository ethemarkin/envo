import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ErrorNote } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { AuthLayout, Divider, GoogleButton } from "./AuthLayout";
import { useAuthConfig, useLogin, useMe } from "./useAuth";

export function LoginPage() {
  const { data: me } = useMe();
  const { data: config } = useAuthConfig();
  const login = useLogin();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  if (me) return <Navigate to="/" replace />;

  const redirectError = params.get("error");

  function submit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ email, password }, { onSuccess: () => navigate("/", { replace: true }) });
  }

  return (
    <AuthLayout title="Envo'ya giriş yapın">
      {config?.google_enabled && (
        <>
          <GoogleButton label="Google ile devam et" />
          <Divider />
        </>
      )}
      <form onSubmit={submit} className="space-y-4">
        {(login.error || redirectError) && (
          <ErrorNote>{errorMessage(login.error ?? redirectError)}</ErrorNote>
        )}
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
            autoComplete="current-password"
            required
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={login.isPending}>
          {login.isPending ? "Giriş yapılıyor…" : "Giriş yap"}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-zinc-600">
        Hesabınız yok mu?{" "}
        <Link to="/register" className="font-medium text-zinc-900 underline-offset-2 hover:underline">
          Kaydolun
        </Link>
      </p>
    </AuthLayout>
  );
}
