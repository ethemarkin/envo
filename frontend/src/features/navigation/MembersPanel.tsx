import { type FormEvent, useState } from "react";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { canManage } from "../../lib/permissions";
import type { Member, Role } from "../../lib/types";
import { useMe } from "../auth/useAuth";
import { useInvitations, useMemberMutations, useMembers } from "./queries";

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
  const { add, update, remove, revokeInvitation } = useMemberMutations(kind, id);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<Role>("developer");
  const manage = canManage(role);
  const invitations = useInvitations(kind, id, manage);
  // Only owners may grant or change the owner role (enforced by the server).
  const assignable = role === "owner" ? ROLES : ROLES.filter((r) => r !== "owner");

  function submit(e: FormEvent) {
    e.preventDefault();
    add.mutate({ email: email.trim(), role: newRole }, { onSuccess: () => setEmail("") });
  }

  const error = add.error ?? update.error ?? remove.error ?? revokeInvitation.error;
  const added = add.data;

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
            Hesabı olan kullanıcılar hemen eklenir. Hesabı olmayanlara 7 gün geçerli bir davet
            bağlantısı gönderilir.
          </p>
        </form>
      )}
      {added?.type === "invitation" && added.invitation && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          {added.invite_url ? (
            <>
              <p>
                <strong>{added.invitation.email}</strong> için davet oluşturuldu, ancak sunucuda
                e-posta yapılandırılmadığı için gönderilemedi. Bu bağlantıyı kendiniz iletin:
              </p>
              <CopyField value={added.invite_url} />
            </>
          ) : (
            <p>
              <strong>{added.invitation.email}</strong> adresine davet e-postası gönderildi.
            </p>
          )}
        </div>
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
      {manage && invitations.data && invitations.data.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-zinc-700">Bekleyen davetler</h3>
          <ul className="card divide-y divide-zinc-100">
            {invitations.data.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{inv.email}</p>
                  <p className="text-xs text-zinc-500">
                    {inv.invited_by ? `${inv.invited_by} davet etti · ` : ""}
                    {new Date(inv.expires_at).toLocaleDateString("tr-TR")} tarihine kadar geçerli
                  </p>
                </div>
                <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
                  {ROLE_LABELS[inv.role]}
                </span>
                <button
                  type="button"
                  className="btn-danger py-1 text-xs"
                  disabled={revokeInvitation.isPending}
                  onClick={() => revokeInvitation.mutate(inv.id)}
                >
                  İptal et
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** Read-only text with a copy button (links, one-time tokens). */
export function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-2 flex gap-2">
      <input
        readOnly
        className="input font-mono text-xs"
        value={value}
        onFocus={(e) => e.target.select()}
      />
      <button
        type="button"
        className="btn-secondary shrink-0"
        onClick={() => {
          navigator.clipboard
            ?.writeText(value)
            .then(() => setCopied(true))
            .catch(() => setCopied(false));
        }}
      >
        {copied ? "Kopyalandı" : "Kopyala"}
      </button>
    </div>
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
