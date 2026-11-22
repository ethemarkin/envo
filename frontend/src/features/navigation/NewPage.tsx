import { type FormEvent, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { Breadcrumbs } from "../../app/Breadcrumbs";
import { ErrorNote, Spinner } from "../../app/ErrorNote";
import { errorMessage } from "../../lib/messages";
import { slugify } from "../../lib/slugify";
import { useCreateGroup, useCreateProject, useGroup, useTree } from "./queries";

/** Create a group or project, at the root or inside ?parent=<group id>. */
export function NewPage() {
  const [params] = useSearchParams();
  const type = params.get("type") === "group" ? "group" : "project";
  const parentId = params.get("parent");
  return parentId ? (
    <NewInGroup type={type} parentId={parentId} />
  ) : (
    <NewAtRoot type={type} />
  );
}

function NewAtRoot({ type }: { type: "group" | "project" }) {
  const tree = useTree();
  if (tree.isPending) return <Spinner />;
  if (tree.data && !tree.data.can_create_root) {
    return <ErrorNote>{errorMessage("root_creation_disabled")}</ErrorNote>;
  }
  return <NewForm type={type} parentId={null} parentPath={null} ancestors={[]} />;
}

function NewInGroup({ type, parentId }: { type: "group" | "project"; parentId: string }) {
  const parent = useGroup(parentId);
  if (parent.isPending) return <Spinner />;
  if (parent.error) return <ErrorNote>{errorMessage(parent.error)}</ErrorNote>;
  const g = parent.data;
  return (
    <NewForm
      type={type}
      parentId={g.id}
      parentPath={g.path}
      ancestors={[...g.ancestors, { id: g.id, name: g.name, slug: g.slug }]}
    />
  );
}

function NewForm({
  type,
  parentId,
  parentPath,
  ancestors,
}: {
  type: "group" | "project";
  parentId: string | null;
  parentPath: string | null;
  ancestors: { id: string; name: string; slug: string }[];
}) {
  const createGroup = useCreateGroup();
  const createProject = useCreateProject();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [description, setDescription] = useState("");
  const mutation = type === "group" ? createGroup : createProject;
  const effectiveSlug = slugEdited ? slug : slugify(name);

  if (mutation.isSuccess) {
    const created = mutation.data;
    return <Navigate to={type === "group" ? `/groups/${created.id}` : `/projects/${created.id}`} replace />;
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const body = {
      name: name.trim(),
      slug: effectiveSlug || undefined,
      description: description.trim() || undefined,
    };
    if (type === "group") createGroup.mutate({ ...body, parent_id: parentId });
    else createProject.mutate({ ...body, group_id: parentId });
  }

  const title = type === "group" ? (parentId ? "Yeni alt group" : "Yeni group") : "Yeni proje";

  return (
    <div className="max-w-xl space-y-6">
      <div className="space-y-1">
        <Breadcrumbs items={ancestors} />
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-zinc-500">
          {type === "group"
            ? "Group'lar projeleri ve alt group'ları bir arada tutar; üyelikler alt seviyelere miras geçer."
            : "Her proje development, staging ve production ortamlarıyla oluşturulur."}
        </p>
      </div>
      <form onSubmit={submit} className="card space-y-4 p-5">
        {mutation.error && <ErrorNote>{errorMessage(mutation.error)}</ErrorNote>}
        <div>
          <label className="label" htmlFor="new-name">
            Ad
          </label>
          <input
            id="new-name"
            className="input"
            required
            autoFocus
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="new-slug">
            Yol
          </label>
          <div className="flex items-center overflow-hidden rounded-md border border-zinc-300 bg-white focus-within:border-zinc-900 focus-within:ring-2 focus-within:ring-zinc-900/10">
            {parentPath && (
              <span className="border-r border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-sm text-zinc-500">
                {parentPath}/
              </span>
            )}
            <input
              id="new-slug"
              className="min-w-0 flex-1 px-3 py-2 font-mono text-sm outline-none"
              pattern="[a-z0-9]([a-z0-9\-]*[a-z0-9])?"
              maxLength={64}
              value={effectiveSlug}
              onChange={(e) => {
                setSlugEdited(true);
                setSlug(e.target.value);
              }}
            />
          </div>
        </div>
        <div>
          <label className="label" htmlFor="new-description">
            Açıklama <span className="font-normal text-zinc-400">(isteğe bağlı)</span>
          </label>
          <textarea
            id="new-description"
            className="input"
            rows={2}
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <button type="submit" className="btn-primary" disabled={!name.trim() || mutation.isPending}>
            Oluştur
          </button>
          <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>
            Vazgeç
          </button>
        </div>
      </form>
    </div>
  );
}
