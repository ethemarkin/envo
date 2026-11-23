import { Link } from "react-router";
import { EmptyState } from "./ErrorNote";

export function NotFound() {
  return (
    <EmptyState title="Page not found">
      <Link to="/" className="underline underline-offset-2">
        Back to home
      </Link>
    </EmptyState>
  );
}
