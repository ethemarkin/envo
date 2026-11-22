import { Link, useNavigate } from "react-router";
import { EmptyState, ErrorNote, Spinner } from "../../app/ErrorNote";
import { InlineCreate } from "../../app/InlineCreate";
import { errorMessage, ROLE_LABELS } from "../../lib/messages";
import { useCreateOrganization, useOrganizations } from "./queries";

export function OrganizationsPage() {
  const { data: orgs, isPending, error } = useOrganizations();
  const create = useCreateOrganization();
  const navigate = useNavigate();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Organizasyonlar</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Projeler ve ekip üyelikleri organizasyon altında yönetilir.
        </p>
      </div>

      <section className="card p-5">
        <h2 className="mb-3 text-sm font-semibold">Yeni organizasyon</h2>
        <InlineCreate
          placeholder="Örn. Acme Yazılım"
          submitLabel="Oluştur"
          pending={create.isPending}
          error={create.error}
          onCreate={(name, reset) =>
            create.mutate(
              { name },
              {
                onSuccess: (org) => {
                  reset();
                  navigate(`/orgs/${org.id}`);
                },
              },
            )
          }
        />
      </section>

      <section>
        {isPending ? (
          <Spinner />
        ) : error ? (
          <ErrorNote>{errorMessage(error)}</ErrorNote>
        ) : orgs.length === 0 ? (
          <EmptyState title="Henüz bir organizasyonunuz yok">
            Başlamak için yukarıdan bir organizasyon oluşturun.
          </EmptyState>
        ) : (
          <ul className="card divide-y divide-zinc-100">
            {orgs.map((org) => (
              <li key={org.id}>
                <Link
                  to={`/orgs/${org.id}`}
                  className="flex items-center justify-between px-5 py-4 hover:bg-zinc-50"
                >
                  <div>
                    <p className="font-medium">{org.name}</p>
                    <p className="font-mono text-xs text-zinc-500">{org.slug}</p>
                  </div>
                  <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
                    {ROLE_LABELS[org.role]}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
