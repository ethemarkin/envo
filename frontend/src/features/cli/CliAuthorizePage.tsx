import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { ErrorNote } from "../../app/ErrorNote";
import { get, post } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import { useMe } from "../auth/useAuth";

interface CliRequest {
  user_code: string;
  client_name: string | null;
  client_ip: string | null;
  created_at: string;
  expires_at: string;
}

/**
 * Approves an `envo login`. The user must type the code shown in their
 * terminal; links never carry it, so nobody can send a ready-to-approve link.
 */
export function CliAuthorizePage() {
  const { data: me } = useMe();
  const [code, setCode] = useState("");
  const [outcome, setOutcome] = useState<"approved" | "denied" | null>(null);

  const lookup = useMutation({
    mutationFn: (userCode: string) =>
      get<CliRequest>(`/api/cli/auth/requests/${encodeURIComponent(userCode)}`),
  });
  const decide = useMutation({
    mutationFn: ({ approve, userCode }: { approve: boolean; userCode: string }) =>
      post<void>(approve ? "/api/cli/auth/approve" : "/api/cli/auth/deny", {
        user_code: userCode,
      }),
    onSuccess: (_, { approve }) => setOutcome(approve ? "approved" : "denied"),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    lookup.mutate(code.trim());
  }

  const request = lookup.data;

  return (
    <div className="mx-auto max-w-md space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">CLI sign-in</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Enter the code shown when you ran <code className="font-mono">envo login</code> in your
          terminal.
        </p>
      </div>

      {outcome === "approved" ? (
        <div className="card space-y-1 p-5">
          <p className="font-medium text-emerald-800">CLI session approved.</p>
          <p className="text-sm text-zinc-600">You can return to your terminal and close this tab.</p>
        </div>
      ) : outcome === "denied" ? (
        <div className="card p-5">
          <p className="font-medium">Request denied. No CLI session was started.</p>
        </div>
      ) : !request ? (
        <form onSubmit={submit} className="card space-y-4 p-5">
          {lookup.error && <ErrorNote>{errorMessage(lookup.error)}</ErrorNote>}
          <div>
            <label htmlFor="code" className="label">
              Verification code
            </label>
            <input
              id="code"
              className="input text-center font-mono text-lg tracking-[0.3em] uppercase"
              placeholder="XXXX-XXXX"
              autoComplete="off"
              autoFocus
              maxLength={9}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={code.trim().length < 8 || lookup.isPending}>
            Continue
          </button>
        </form>
      ) : (
        <div className="card space-y-4 p-5">
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Approve only if you started this request yourself. If you approve, the CLI on this device
            will act with the permissions of your account{" "}
            <strong>{me?.email}</strong>.
          </div>
          <dl className="grid grid-cols-[7rem_1fr] gap-y-2 text-sm">
            <dt className="text-zinc-500">Code</dt>
            <dd className="font-mono">{request.user_code}</dd>
            <dt className="text-zinc-500">Device</dt>
            <dd>{request.client_name ?? "—"}</dd>
            <dt className="text-zinc-500">IP address</dt>
            <dd className="font-mono">{request.client_ip ?? "—"}</dd>
            <dt className="text-zinc-500">Time</dt>
            <dd>{new Date(request.created_at).toLocaleString("en-US")}</dd>
          </dl>
          {decide.error && <ErrorNote>{errorMessage(decide.error)}</ErrorNote>}
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-primary flex-1"
              disabled={decide.isPending}
              onClick={() => decide.mutate({ approve: true, userCode: request.user_code })}
            >
              Approve
            </button>
            <button
              type="button"
              className="btn-secondary flex-1"
              disabled={decide.isPending}
              onClick={() => decide.mutate({ approve: false, userCode: request.user_code })}
            >
              Deny
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
