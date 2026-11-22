import { Link } from "react-router";
import { EmptyState } from "./ErrorNote";

export function NotFound() {
  return (
    <EmptyState title="Sayfa bulunamadı">
      <Link to="/" className="underline underline-offset-2">
        Organizasyonlara dön
      </Link>
    </EmptyState>
  );
}
