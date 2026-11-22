import { type FormEvent, useState } from "react";
import { errorMessage } from "../lib/messages";
import { ErrorNote } from "./ErrorNote";

/** A one-field "create" form: name input + submit button. */
export function InlineCreate({
  placeholder,
  submitLabel,
  pending,
  error,
  onCreate,
}: {
  placeholder: string;
  submitLabel: string;
  pending: boolean;
  error: unknown;
  onCreate: (name: string, reset: () => void) => void;
}) {
  const [name, setName] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed) onCreate(trimmed, () => setName(""));
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex gap-2">
        <input
          className="input"
          placeholder={placeholder}
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" className="btn-primary shrink-0" disabled={pending || !name.trim()}>
          {submitLabel}
        </button>
      </div>
      {error != null && <ErrorNote>{errorMessage(error)}</ErrorNote>}
    </form>
  );
}
