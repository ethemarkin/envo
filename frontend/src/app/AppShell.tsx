import { useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useLogout, useMe } from "../features/auth/useAuth";
import { Sidebar } from "../features/navigation/Sidebar";
import { Spinner } from "./ErrorNote";
import { Logo } from "./Logo";

export function AppShell() {
  const { data: me, isPending } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  if (isPending) return <Spinner />;
  if (!me) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="z-20 shrink-0 border-b border-zinc-200 bg-white">
        <div className="flex h-14 items-center gap-4 px-4">
          <button
            type="button"
            className="btn-secondary px-2 py-1.5 md:hidden"
            aria-label="Open menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
              <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
          <Link to="/" aria-label="Home">
            <Logo className="h-7" />
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `rounded-md px-2.5 py-1.5 text-sm ${isActive ? "bg-zinc-100 font-medium" : "text-zinc-600 hover:text-zinc-900"}`
              }
            >
              Settings
            </NavLink>
            <span className="hidden text-sm text-zinc-500 sm:inline">{me.email}</span>
            <button
              type="button"
              className="btn-secondary py-1.5"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {/* Desktop: fixed column. Mobile: slide-over toggled from the header. */}
        <aside
          className={`${menuOpen ? "absolute inset-y-0 left-0 z-10 shadow-xl" : "hidden"} w-72 shrink-0 border-r border-zinc-200 bg-zinc-100 md:static md:block md:shadow-none`}
        >
          <Sidebar onNavigate={() => setMenuOpen(false)} />
        </aside>
        {menuOpen && (
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 z-0 bg-black/20 md:hidden"
            onClick={() => setMenuOpen(false)}
          />
        )}
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-4 py-8 md:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
