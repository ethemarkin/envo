import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useLogout, useMe } from "../features/auth/useAuth";
import { Spinner } from "./ErrorNote";
import { Logo } from "./Logo";

export function AppShell() {
  const { data: me, isPending } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();

  if (isPending) return <Spinner />;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-2.5 py-1.5 text-sm ${isActive ? "bg-zinc-100 font-medium text-zinc-900" : "text-zinc-600 hover:text-zinc-900"}`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
          <Link to="/" aria-label="Ana sayfa">
            <Logo className="h-7" />
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navClass}>
              Organizasyonlar
            </NavLink>
            <NavLink to="/settings" className={navClass}>
              Ayarlar
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-zinc-500 sm:inline">{me.email}</span>
            <button
              type="button"
              className="btn-secondary py-1.5"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              Çıkış
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
