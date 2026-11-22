import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";
import { ErrorNote } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { useDeleteNode, useUpdateNode } from "./queries";

/** Rename / re-slug and delete for a group or project. */
export function NodeSettings({
  kind,
  id,
  name,
  slug,
  path,
  description,
  canUpdate,
  canDelete,
  afterDelete,
}: {
  kind: "groups" | "projects";
  id: string;
  name: string;
  slug: string;
  path: string;
  description: string | null;
  canUpdate: boolean;
  canDelete: boolean;
  afterDelete: string;
}) {
  const update = useUpdateNode(kind, id);
  const remove = useDeleteNode(kind, id);
  const navigate = useNavigate();
  const [form, setForm] = useState({ name, slug, description: description ?? "" });
  const dirty =
    form.name !== name || form.slug !== slug || form.description !== (description ?? "");
  const noun = kind === "groups" ? "group" : "proje";

  if (!canUpdate && !canDelete) return null;

  function save(e: FormEvent) {
    e.preventDefault();
    update.mutate({
      name: form.name.trim(),
      slug: form.slug.trim(),
      description: form.description.trim() || null,
    });
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Ayarlar</h2>
      {canUpdate && (
        <form onSubmit={save} className="card space-y-4 p-5">
          {update.error && <ErrorNote>{errorMessage(update.error)}</ErrorNote>}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor={`${id}-name`}>
                Ad
              </label>
              <input
                id={`${id}-name`}
                className="input"
                required
                maxLength={100}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor={`${id}-slug`}>
                Kısa ad (yol)
              </label>
              <input
                id={`${id}-slug`}
                className="input font-mono"
                required
                pattern="[a-z0-9]([a-z0-9\-]*[a-z0-9])?"
                maxLength={64}
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
              />
              {form.slug !== slug && (
                <p className="mt-1.5 text-xs text-amber-700">
                  Yol değişir; bu yolu kullanan envo.yaml dosyaları kimlikle bağlı olduğu için
                  çalışmaya devam eder.
                </p>
              )}
            </div>
          </div>
          <div>
            <label className="label" htmlFor={`${id}-description`}>
              Açıklama
            </label>
            <textarea
              id={`${id}-description`}
              className="input"
              rows={2}
              maxLength={2000}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={!dirty || update.isPending}>
            Kaydet
          </button>
        </form>
      )}
      {canDelete && (
        <div className="card border-red-200 p-5">
          <h3 className="text-sm font-semibold text-red-800">
            {kind === "groups" ? "Group'u sil" : "Projeyi sil"}
          </h3>
          <p className="mt-1 text-sm text-zinc-600">
            {kind === "groups"
              ? "Tüm alt group'lar, projeler, ortamlar ve değişkenler kalıcı olarak silinir."
              : "Projenin tüm ortamları ve değişkenleri kalıcı olarak silinir."}
          </p>
          {remove.error && <ErrorNote>{errorMessage(remove.error)}</ErrorNote>}
          <button
            type="button"
            className="btn-danger mt-3"
            disabled={remove.isPending}
            onClick={() => {
              const typed = window.prompt(`Silmek için ${noun} yolunu yazın: ${path}`);
              if (typed === path) remove.mutate(undefined, { onSuccess: () => navigate(afterDelete) });
            }}
          >
            {kind === "groups" ? "Group'u sil" : "Projeyi sil"}
          </button>
        </div>
      )}
    </section>
  );
}
