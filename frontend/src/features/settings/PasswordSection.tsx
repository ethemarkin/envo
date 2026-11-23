import { type FormEvent, useState } from "react";
import { ErrorNote } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { MIN_PASSWORD, useChangePassword } from "../auth/useAuth";

export function PasswordSection() {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const mismatch = confirm.length > 0 && next !== confirm;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (next !== confirm) return;
    setDone(false);
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
          setConfirm("");
          setDone(true);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3 px-5 py-4">
      <h2 className="text-sm font-semibold">Password</h2>
      <p className="text-sm text-zinc-600">
        Changing your password signs out your sessions on other devices and in the CLI.
      </p>
      {change.error && <ErrorNote>{errorMessage(change.error)}</ErrorNote>}
      {done && (
        <p role="status" className="text-sm text-emerald-700">
          Your password has been changed.
        </p>
      )}
      <div className="grid max-w-sm gap-3">
        <div>
          <label htmlFor="current-password" className="label">
            Current password
          </label>
          <input
            id="current-password"
            type="password"
            autoComplete="current-password"
            required
            className="input"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="new-password" className="label">
            New password
          </label>
          <input
            id="new-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            className="input"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <p className="mt-1.5 text-xs text-zinc-500">At least {MIN_PASSWORD} characters.</p>
        </div>
        <div>
          <label htmlFor="confirm-password" className="label">
            Confirm new password
          </label>
          <input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            required
            className="input"
            aria-invalid={mismatch}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          {mismatch && <p className="mt-1.5 text-xs text-red-600">Passwords do not match.</p>}
        </div>
      </div>
      <button type="submit" className="btn-primary" disabled={change.isPending || mismatch}>
        {change.isPending ? "Changing…" : "Change password"}
      </button>
    </form>
  );
}
