import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, get, post } from "../../lib/api";
import type { User } from "../../lib/types";

export const ME_KEY = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await get<User>("/api/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      post<User>("/api/auth/login", body),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(ME_KEY, user);
    },
  });
}

export function useSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string; name?: string }) =>
      post<User>("/api/auth/signup", body),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(ME_KEY, user);
    },
  });
}

export function useLogout(all = false) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => post<void>(all ? "/api/auth/logout-all" : "/api/auth/logout"),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(ME_KEY, null);
    },
  });
}
