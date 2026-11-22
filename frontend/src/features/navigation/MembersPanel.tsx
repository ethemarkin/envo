import { type FormEvent, useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { canManage } from "../../lib/permissions";
import type { Member, Role } from "../../lib/types";
import { useMe } from "../auth/useAuth";
import { useMemberMutations, useMembers } from "./queries";

const ROLES: Role[] = ["owner", "admin", "developer", "viewer"];

/**
 * Direct members of a group or project plus members inherited from parent
 * groups. Inherited memberships are changed on the group they come from.
 */
export function MembersPanel({
  kind,
  id,
  role,
}: {
  kind: "groups" | "projects";
  id: string;
  role: Role;
}) {
  const { data: me } = useMe();
  const members = useMembers(kind, id);
  const { add, update, remove } = useMemberMutations(kind, id);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<Role>("developer");
  const manage = canManage(role);
  // Only owners may grant or change the owner role (enforced by the server).
  const assignable = role === "owner" ? ROLES : ROLES.filter((r) => r !== "owner");

  function submit(e: FormEvent) {
    e.preventDefault();
    add.mutate({ email: email.trim(), role: newRole }, { onSuccess: () => setEmail("") });
  }

  const error = add.error ?? update.error ?? remove.error;

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Üyeler</h2>
      {manage && (
        <form onSubmit={submit} className="card flex flex-wrap gap-2 p-4">
          <input
            type="email"
            required
            placeholder="kullanici@ornek.com"
            className="input min-w-48 flex-1"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-label="Eklenecek kullanıcının e-postası"
          />
          <select
            className="input w-auto"
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as Role)}
            aria-label="Rol"
          >
            {assignable.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
          <button type="submit" className="btn-primary" disabled={add.isPending || !email.trim()}>
            Üye ekle
          </button>
          <p className="w-full text-xs text-zinc-500">
            Kullanıcının Envo hesabı olmalı. Davet e-postaları ekip yönetimi fazında eklenecek.
          </p>
        </form>
      )}
      {error && <ErrorNote>{errorMessage(error)}</ErrorNote>}
      {members.isPending ? (
        <Spinner />
      ) : members.error ? (
        <ErrorNote>{errorMessage(members.error)}</ErrorNote>
      ) : (
        <ul className="card divide-y divide-zinc-100">
          {members.data.map((m) => (
            <MemberRow
              key={`${m.source_id}-${m.id}`}
              member={m}
              canEdit={manage && !m.inherited && (role === "owner" || m.role !== "owner")}
              isMe={m.user_id === me?.id}
              assignable={assignable}
              busy={update.isPending || remove.isPending}
              onRole={(r) => update.mutate({ memberId: m.id, role: r })}
              onRemove={() => {
                const prompt =
                  m.user_id === me?.id
                    ? "Bu üyelikten ayrılmak istiyor musunuz?"
                    : `${m.email} kaldırılsın mı?`;
                if (window.confirm(prompt)) remove.mutate(m.id);
              }}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function MemberRow({
  member: m,
  canEdit,
  isMe,
  assignable,
  busy,
  onRole,
  onRemove,
}: {
  member: Member;
  canEdit: boolean;
  isMe: boolean;
  assignable: Role[];
  busy: boolean;
  onRole: (r: Role) => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          {m.name ?? m.email}
          {isMe && <span className="ml-1.5 text-xs font-normal text-zinc-500">(siz)</span>}
        </p>
        <p className="truncate text-xs text-zinc-500">
          {m.name ? `${m.email} · ` : ""}
          {m.inherited ? `"${m.source_name}" grubundan miras` : "Doğrudan üye"}
        </p>
      </div>
      {canEdit ? (
        <select
          className="input w-auto py-1"
          value={m.role}
          disabled={busy}
          onChange={(e) => onRole(e.target.value as Role)}
          aria-label={`${m.email} rolü`}
        >
          {assignable.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>
      ) : (
        <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
          {ROLE_LABELS[m.role]}
        </span>
      )}
      {!m.inherited && (canEdit || isMe) && (
        <button type="button" className="btn-danger py-1 text-xs" disabled={busy} onClick={onRemove}>
          {isMe ? "Ayrıl" : "Kaldır"}
        </button>
      )}
    </li>
  );
}
