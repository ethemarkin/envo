import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, patch, post } from "../../lib/api";
import type { Member, Organization, Project, Role } from "../../lib/types";

export const orgKeys = {
  all: ["orgs"] as const,
  one: (orgId: string) => ["orgs", orgId] as const,
  members: (orgId: string) => ["orgs", orgId, "members"] as const,
  projects: (orgId: string) => ["orgs", orgId, "projects"] as const,
};

export function useOrganizations() {
  return useQuery({ queryKey: orgKeys.all, queryFn: () => get<Organization[]>("/api/orgs") });
}

export function useOrganization(orgId: string) {
  return useQuery({
    queryKey: orgKeys.one(orgId),
    queryFn: () => get<Organization>(`/api/orgs/${orgId}`),
  });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) => post<Organization>("/api/orgs", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: orgKeys.all }),
  });
}

export function useMembers(orgId: string) {
  return useQuery({
    queryKey: orgKeys.members(orgId),
    queryFn: () => get<Member[]>(`/api/orgs/${orgId}/members`),
  });
}

export function useUpdateMember(orgId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: Role }) =>
      patch<Member>(`/api/orgs/${orgId}/members/${memberId}`, { role }),
    onSettled: () => qc.invalidateQueries({ queryKey: orgKeys.members(orgId) }),
  });
}

export function useProjects(orgId: string) {
  return useQuery({
    queryKey: orgKeys.projects(orgId),
    queryFn: () => get<Project[]>(`/api/orgs/${orgId}/projects`),
  });
}

export function useCreateProject(orgId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      post<Project>(`/api/orgs/${orgId}/projects`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: orgKeys.projects(orgId) }),
  });
}

export function useDeleteOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orgId: string) => del(`/api/orgs/${orgId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: orgKeys.all }),
  });
}
