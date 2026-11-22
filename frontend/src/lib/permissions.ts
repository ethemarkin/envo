import type { Role } from "./types";

// UI hints only: the server enforces every rule (see backend policy.py).
export const canManage = (role: Role) => role === "owner" || role === "admin";
