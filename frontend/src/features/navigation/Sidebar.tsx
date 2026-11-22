import { useMemo, useState } from "react";
import { Link, NavLink, useLocation } from "react-router";
import type { TreeNode } from "../../lib/types";
import { useTree } from "./queries";

interface Branch {
  group: TreeNode;
  groups: Branch[];
  projects: TreeNode[];
}

function buildTree(groups: TreeNode[], projects: TreeNode[]) {
  const byParent = new Map<string | null, TreeNode[]>();
  for (const g of groups) {
    const list = byParent.get(g.parent_id) ?? [];
    list.push(g);
    byParent.set(g.parent_id, list);
  }
  const projectsByGroup = new Map<string | null, TreeNode[]>();
  for (const p of projects) {
    const list = projectsByGroup.get(p.parent_id) ?? [];
    list.push(p);
    projectsByGroup.set(p.parent_id, list);
  }
  const byName = (a: TreeNode, b: TreeNode) => a.name.localeCompare(b.name, "tr");
  const branch = (g: TreeNode): Branch => ({
    group: g,
    groups: (byParent.get(g.id) ?? []).sort(byName).map(branch),
    projects: (projectsByGroup.get(g.id) ?? []).sort(byName),
  });
  return {
    roots: (byParent.get(null) ?? []).sort(byName).map(branch),
    rootProjects: (projectsByGroup.get(null) ?? []).sort(byName),
  };
}

/** Group ids on the path to the current page, so they start expanded. */
function useActivePath(groups: TreeNode[], projects: TreeNode[]): Set<string> {
  const { pathname } = useLocation();
  return useMemo(() => {
    const parent = new Map(groups.map((g) => [g.id, g.parent_id]));
    const open = new Set<string>();
    const match = /^\/(groups|projects)\/([^/]+)/.exec(pathname);
    if (!match) return open;
    let id: string | null | undefined =
      match[1] === "groups" ? match[2] : projects.find((p) => p.id === match[2])?.parent_id;
    while (id) {
      open.add(id);
      id = parent.get(id);
    }
    return open;
  }, [pathname, groups, projects]);
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { data: tree, isPending, error } = useTree();
  const activePath = useActivePath(tree?.groups ?? [], tree?.projects ?? []);
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const structure = useMemo(
    () => buildTree(tree?.groups ?? [], tree?.projects ?? []),
    [tree],
  );

  const isOpen = (id: string) => toggled[id] ?? activePath.has(id);
  const toggle = (id: string) => setToggled((t) => ({ ...t, [id]: !isOpen(id) }));

  return (
    <nav aria-label="Gruplar ve projeler" className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 pt-4 pb-2">
        <span className="text-xs font-semibold tracking-wide text-zinc-500 uppercase">
          Gruplar ve projeler
        </span>
        {tree?.can_create_root && (
          <div className="flex gap-1">
            <Link
              to="/new?type=group"
              onClick={onNavigate}
              className="rounded px-1.5 py-0.5 text-xs text-zinc-600 hover:bg-zinc-200"
              title="Yeni group"
            >
              + Group
            </Link>
            <Link
              to="/new?type=project"
              onClick={onNavigate}
              className="rounded px-1.5 py-0.5 text-xs text-zinc-600 hover:bg-zinc-200"
              title="Yeni proje"
            >
              + Proje
            </Link>
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {isPending ? (
          <p className="px-2 py-1 text-sm text-zinc-400">Yükleniyor…</p>
        ) : error ? (
          <p className="px-2 py-1 text-sm text-red-700">Ağaç yüklenemedi.</p>
        ) : structure.roots.length + structure.rootProjects.length === 0 ? (
          <p className="px-2 py-1 text-sm text-zinc-500">Henüz group veya proje yok.</p>
        ) : (
          <ul role="tree" className="space-y-0.5">
            {structure.roots.map((b) => (
              <GroupBranch
                key={b.group.id}
                branch={b}
                depth={0}
                isOpen={isOpen}
                toggle={toggle}
                onNavigate={onNavigate}
              />
            ))}
            {structure.rootProjects.map((p) => (
              <ProjectLeaf key={p.id} project={p} depth={0} onNavigate={onNavigate} />
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}

const rowClass = (active: boolean, muted = false) =>
  `flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 pr-2 text-sm ${
    active ? "bg-zinc-900 text-white" : muted ? "text-zinc-400" : "text-zinc-700 hover:bg-zinc-200"
  }`;

function GroupBranch({
  branch,
  depth,
  isOpen,
  toggle,
  onNavigate,
}: {
  branch: Branch;
  depth: number;
  isOpen: (id: string) => boolean;
  toggle: (id: string) => void;
  onNavigate?: () => void;
}) {
  const { group } = branch;
  const open = isOpen(group.id);
  const hasChildren = branch.groups.length + branch.projects.length > 0;
  const accessible = group.role !== null;
  const indent = { paddingLeft: `${depth * 14 + 4}px` };

  return (
    <li role="treeitem" aria-expanded={hasChildren ? open : undefined}>
      <div className="flex items-center" style={indent}>
        <button
          type="button"
          onClick={() => toggle(group.id)}
          disabled={!hasChildren}
          aria-label={open ? `${group.name} daralt` : `${group.name} genişlet`}
          className="flex size-5 shrink-0 items-center justify-center rounded text-zinc-400 hover:text-zinc-900 disabled:invisible"
        >
          <svg viewBox="0 0 16 16" className={`size-3 transition-transform ${open ? "rotate-90" : ""}`}>
            <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" />
          </svg>
        </button>
        {accessible ? (
          <NavLink
            to={`/groups/${group.id}`}
            onClick={onNavigate}
            className={({ isActive }) => rowClass(isActive) + " pl-1"}
            title={group.path}
          >
            <FolderIcon />
            <span className="truncate">{group.name}</span>
          </NavLink>
        ) : (
          <span className={rowClass(false, true) + " pl-1"} title={`${group.path} (erişiminiz yok)`}>
            <FolderIcon />
            <span className="truncate">{group.name}</span>
          </span>
        )}
      </div>
      {open && hasChildren && (
        <ul role="group" className="space-y-0.5">
          {branch.groups.map((b) => (
            <GroupBranch
              key={b.group.id}
              branch={b}
              depth={depth + 1}
              isOpen={isOpen}
              toggle={toggle}
              onNavigate={onNavigate}
            />
          ))}
          {branch.projects.map((p) => (
            <ProjectLeaf key={p.id} project={p} depth={depth + 1} onNavigate={onNavigate} />
          ))}
        </ul>
      )}
    </li>
  );
}

function ProjectLeaf({
  project,
  depth,
  onNavigate,
}: {
  project: TreeNode;
  depth: number;
  onNavigate?: () => void;
}) {
  return (
    <li role="treeitem" className="flex" style={{ paddingLeft: `${depth * 14 + 24}px` }}>
      <NavLink
        to={`/projects/${project.id}`}
        onClick={onNavigate}
        className={({ isActive }) => rowClass(isActive) + " pl-1"}
        title={project.path}
      >
        <ProjectIcon />
        <span className="truncate">{project.name}</span>
      </NavLink>
    </li>
  );
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4 shrink-0 opacity-70" aria-hidden="true">
      <path
        d="M1.75 3.5h4l1.5 1.5h7v7.75a.75.75 0 0 1-.75.75H2.5a.75.75 0 0 1-.75-.75z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ProjectIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4 shrink-0 opacity-70" aria-hidden="true">
      <rect x="2.25" y="2.25" width="11.5" height="11.5" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 6h6M5 8.5h6M5 11h3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}
