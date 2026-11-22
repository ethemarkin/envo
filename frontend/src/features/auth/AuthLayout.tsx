import type { ReactNode } from "react";
import { Logo } from "../../app/Logo";

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo className="h-9" />
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        </div>
        <div className="card p-6">{children}</div>
      </div>
    </div>
  );
}

/** Only same-app paths are accepted as a post-login destination. */
export function safeRedirect(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from;
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//") ? from : "/";
}
