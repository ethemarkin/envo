import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, get, post } from "../../lib/api";
import type { User } from "../../lib/types";

export const ME_KEY = ["me"] as const;

/** Minimum password length; the API enforces the same limit. */
export const MIN_PASSWORD = 8;

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

/** Whether signing up needs an invitation (always, except on an empty instance). */
export function useRegistration() {
  return useQuery({
    queryKey: ["registration"],
    queryFn: () => get<{ invitation_required: boolean }>("/api/auth/registration"),
    staleTime: 60 * 1000,
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
    mutationFn: (body: { email: string; password: string; name?: string; invite_token?: string }) =>
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

/** Signs out every other session; this browser receives fresh cookies. */
export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      post<void>("/api/auth/password", body),
  });
}
