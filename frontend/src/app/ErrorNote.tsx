import type { ReactNode } from "react";

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {children}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 px-6 py-10 text-center">
      <p className="font-medium text-zinc-800">{title}</p>
      {children && <div className="mt-1 text-sm text-zinc-500">{children}</div>}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex justify-center py-10" aria-label="Loading…">
      <div className="size-5 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
    </div>
  );
}
