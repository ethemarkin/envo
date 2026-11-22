import type { Visibility } from "../../lib/types";

export function VisibilityToggle({
  value,
  onChange,
  disabled,
}: {
  value: Visibility;
  onChange: (v: Visibility) => void;
  disabled?: boolean;
}) {
  const option = (v: Visibility, label: string) => (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={value === v}
      onClick={() => onChange(v)}
      className={`px-2 py-1 text-xs transition-colors disabled:cursor-not-allowed ${
        value === v ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 hover:bg-zinc-100"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-zinc-300">
      {option("secret", "Gizli")}
      {option("visible", "Görünür")}
    </div>
  );
}

export function VisibilityBadge({ value }: { value: Visibility }) {
  return value === "secret" ? (
    <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-xs text-white">Gizli</span>
  ) : (
    <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700">Görünür</span>
  );
}
