import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { del, get, post } from "../../lib/api";
import { errorMessage } from "../../lib/messages";
import type { Environment, ServiceToken } from "../../lib/types";
import { CopyField } from "../navigation/MembersPanel";

const EXPIRY_OPTIONS: { label: string; days: number | null }[] = [
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "1 year", days: 365 },
  { label: "No expiration", days: null },
];

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("en-US") : "—";
}

function status(t: ServiceToken): { label: string; className: string } {
  if (t.revoked_at) return { label: "Revoked", className: "bg-zinc-100 text-zinc-500" };
  if (t.expires_at && new Date(t.expires_at) <= new Date()) {
    return { label: "Expired", className: "bg-zinc-100 text-zinc-500" };
  }
  return { label: "Active", className: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" };
}

/** CI/CD credentials scoped to this project's selected environments. */
export function ServiceTokensPanel({
  projectId,
  environments,
}: {
  projectId: string;
  environments: Environment[];
}) {
  const base = `/api/projects/${projectId}/service-tokens`;
  const key = ["projects", projectId, "service-tokens"];
  const qc = useQueryClient();
  const tokens = useQuery({ queryKey: key, queryFn: () => get<ServiceToken[]>(base) });
  const create = useMutation({
    mutationFn: (body: {
      name: string;
      environment_ids: string[];
      can_write: boolean;
      expires_in_days: number | null;
    }) => post<{ token: string; service_token: ServiceToken }>(base, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => del(`${base}/${id}`),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });

  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [canWrite, setCanWrite] = useState(false);
  const [expiry, setExpiry] = useState<number | null>(90);

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      {
        name: name.trim(),
        environment_ids: [...selected],
        can_write: canWrite,
        expires_in_days: expiry,
      },
      {
        onSuccess: () => {
          setName("");
          setSelected(new Set());
          setCanWrite(false);
        },
      },
    );
  }

  const protectedSelected = environments.some((e) => e.protected && selected.has(e.id));

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Service tokens</h2>
        <p className="mt-1 text-sm text-zinc-500">
          For CI/CD: accesses only the selected environments and has no role. Set it in CI as{" "}
          <code className="font-mono">ENVO_TOKEN</code>.
        </p>
      </div>

      {create.data && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p>
            <strong>{create.data.service_token.name}</strong> created. The token is shown only now;
            copy it into your CI secrets before leaving this page.
          </p>
          <CopyField value={create.data.token} />
        </div>
      )}

      <form onSubmit={submit} className="card space-y-4 p-5">
        {create.error && <ErrorNote>{errorMessage(create.error)}</ErrorNote>}
        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <div>
            <label className="label" htmlFor="token-name">
              Name
            </label>
            <input
              id="token-name"
              className="input"
              placeholder="e.g. github-actions-deploy"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="token-expiry">
              Expiration
            </label>
            <select
              id="token-expiry"
              className="input"
              value={expiry ?? "never"}
              onChange={(e) => setExpiry(e.target.value === "never" ? null : Number(e.target.value))}
            >
              {EXPIRY_OPTIONS.map((o) => (
                <option key={o.label} value={o.days ?? "never"}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <fieldset>
          <legend className="label">Environments</legend>
          <div className="flex flex-wrap gap-2">
            {environments.map((env) => (
              <label
                key={env.id}
                className="flex cursor-pointer items-center gap-2 rounded-md border border-zinc-300 px-3 py-1.5 text-sm has-[:checked]:border-zinc-900 has-[:checked]:bg-zinc-50"
              >
                <input
                  type="checkbox"
                  checked={selected.has(env.id)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(env.id);
                    else next.delete(env.id);
                    setSelected(next);
                  }}
                />
                {env.name}
                {env.protected && <span className="text-xs text-amber-700">protected</span>}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={canWrite}
            onChange={(e) => setCanWrite(e.target.checked)}
          />
          <span>
            Write access <span className="text-zinc-500">(push and set; read-only when off)</span>
          </span>
        </label>
        {protectedSelected && (
          <p className="text-xs text-amber-700">
            You selected a protected environment: the token will be able to read its secret values.
          </p>
        )}
        {expiry === null && (
          <p className="text-xs text-amber-700">
            Tokens that never expire stay valid until you revoke them, even if leaked.
          </p>
        )}
        <button
          type="submit"
          className="btn-primary"
          disabled={!name.trim() || selected.size === 0 || create.isPending}
        >
          Create token
        </button>
      </form>

      {revoke.error && <ErrorNote>{errorMessage(revoke.error)}</ErrorNote>}
      {tokens.isPending ? (
        <Spinner />
      ) : tokens.error ? (
        <ErrorNote>{errorMessage(tokens.error)}</ErrorNote>
      ) : tokens.data.length > 0 ? (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Scope</th>
                <th className="px-4 py-2.5 font-medium">Last used</th>
                <th className="px-4 py-2.5 font-medium">Expires</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {tokens.data.map((t) => {
                const s = status(t);
                const active = s.label === "Active";
                return (
                  <tr key={t.id} className={active ? undefined : "text-zinc-400"}>
                    <td className="px-4 py-2.5 align-top">
                      <p className="font-medium">{t.name}</p>
                      <p className="font-mono text-xs text-zinc-500">envo_st_{t.hint}…</p>
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      <p>{t.environments.map((e) => e.slug).join(", ")}</p>
                      <p className="text-xs text-zinc-500">{t.can_write ? "read + write" : "read only"}</p>
                    </td>
                    <td className="px-4 py-2.5 align-top">{formatDate(t.last_used_at)}</td>
                    <td className="px-4 py-2.5 align-top">
                      {t.expires_at ? formatDate(t.expires_at) : "Never"}
                    </td>
                    <td className="px-4 py-2.5 text-right align-top">
                      {active ? (
                        <button
                          type="button"
                          className="btn-danger py-1 text-xs"
                          disabled={revoke.isPending}
                          onClick={() => {
                            if (window.confirm(`Revoke "${t.name}"? Jobs using this token will stop working.`)) {
                              revoke.mutate(t.id);
                            }
                          }}
                        >
                          Revoke
                        </button>
                      ) : (
                        <span className={`rounded-full px-2 py-0.5 text-xs ${s.className}`}>{s.label}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
