import { Link } from "react-router";
import type { Breadcrumb } from "../lib/types";

/** Ancestor groups as links, e.g. "acme / backend /". */
export function Breadcrumbs({ items }: { items: Breadcrumb[] }) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="Konum" className="flex flex-wrap items-center gap-1 text-sm text-zinc-500">
      {items.map((b) => (
        <span key={b.id} className="flex items-center gap-1">
          <Link to={`/groups/${b.id}`} className="hover:text-zinc-900 hover:underline">
            {b.name}
          </Link>
          <span aria-hidden="true">/</span>
        </span>
      ))}
    </nav>
  );
}
