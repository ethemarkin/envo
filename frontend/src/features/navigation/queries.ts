import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, patch, post } from "../../lib/api";
import type {
  AddMemberResult,
  Group,
  GroupChild,
  Invitation,
  Member,
  Project,
  Role,
  Tree,
} from "../../lib/types";

export const keys = {
  tree: ["tree"] as const,
  group: (id: string) => ["groups", id] as const,
  children: (id: string) => ["groups", id, "children"] as const,
  project: (id: string) => ["projects", id] as const,
  members: (kind: "groups" | "projects", id: string) => [kind, id, "members"] as const,
  invitations: (kind: "groups" | "projects", id: string) => [kind, id, "invitations"] as const,
};

export function useTree() {
  return useQuery({ queryKey: keys.tree, queryFn: () => get<Tree>("/api/tree") });
}

export function useGroup(groupId: string) {
  return useQuery({
    queryKey: keys.group(groupId),
    queryFn: () => get<Group>(`/api/groups/${groupId}`),
  });
}

export function useGroupChildren(groupId: string) {
  return useQuery({
    queryKey: keys.children(groupId),
    queryFn: () => get<GroupChild[]>(`/api/groups/${groupId}/children`),
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: keys.project(projectId),
    queryFn: () => get<Project>(`/api/projects/${projectId}`),
  });
}

/** Creating, renaming or deleting anything changes the tree and listings. */
function useInvalidateStructure() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.tree });
    qc.invalidateQueries({ queryKey: ["groups"] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };
}

export interface CreateBody {
  name: string;
  slug?: string;
  description?: string;
}

export function useCreateGroup() {
  const invalidate = useInvalidateStructure();
  return useMutation({
    mutationFn: (body: CreateBody & { parent_id: string | null }) => post<Group>("/api/groups", body),
    onSuccess: invalidate,
  });
}

export function useCreateProject() {
  const invalidate = useInvalidateStructure();
  return useMutation({
    mutationFn: (body: CreateBody & { group_id: string | null }) =>
      post<Project>("/api/projects", body),
    onSuccess: invalidate,
  });
}

export function useUpdateNode(kind: "groups" | "projects", id: string) {
  const invalidate = useInvalidateStructure();
  return useMutation({
    mutationFn: (body: { name?: string; slug?: string; description?: string | null }) =>
      patch<Group | Project>(`/api/${kind}/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteNode(kind: "groups" | "projects", id: string) {
  const invalidate = useInvalidateStructure();
  return useMutation({
    mutationFn: () => del(`/api/${kind}/${id}`),
    onSuccess: invalidate,
  });
}

// --- Members ------------------------------------------------------------------

export function useMembers(kind: "groups" | "projects", id: string) {
  return useQuery({
    queryKey: keys.members(kind, id),
    queryFn: () => get<Member[]>(`/api/${kind}/${id}/members`),
  });
}

export function useInvitations(kind: "groups" | "projects", id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.invitations(kind, id),
    queryFn: () => get<Invitation[]>(`/api/${kind}/${id}/invitations`),
    enabled,
  });
}

export function useMemberMutations(kind: "groups" | "projects", id: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: keys.members(kind, id) });
    qc.invalidateQueries({ queryKey: keys.invitations(kind, id) });
    qc.invalidateQueries({ queryKey: keys.tree });
  };
  const base = `/api/${kind}/${id}/members`;
  return {
    add: useMutation({
      mutationFn: (body: { email: string; role: Role }) => post<AddMemberResult>(base, body),
      onSuccess: invalidate,
    }),
    revokeInvitation: useMutation({
      mutationFn: (invitationId: string) => del(`/api/${kind}/${id}/invitations/${invitationId}`),
      onSettled: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ memberId, role }: { memberId: string; role: Role }) =>
        patch<Member>(`${base}/${memberId}`, { role }),
      onSettled: invalidate,
    }),
    remove: useMutation({
      mutationFn: (memberId: string) => del(`${base}/${memberId}`),
      onSettled: invalidate,
    }),
  };
}
