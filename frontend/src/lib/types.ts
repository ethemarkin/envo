// Mirrors the backend response models (see /api/docs). To be replaced by
// types generated from the OpenAPI schema once the API surface settles.

export type Role = "owner" | "admin" | "developer" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string | null;
  email_verified: boolean;
  has_password: boolean;
  providers: string[];
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: Role;
  created_at: string;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  name: string | null;
  role: Role;
  created_at: string;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Environment {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  protected: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
}

export type Visibility = "visible" | "secret";

export interface Variable {
  key: string;
  visibility: Visibility;
  /** Null for secrets until revealed. */
  value: string | null;
  updated_at: string;
}

export interface VariableList {
  revision: number;
  protected: boolean;
  can_read_secrets: boolean;
  can_write: boolean;
  variables: Variable[];
}

export interface WriteResult {
  revision: number;
  created: string[];
  updated: string[];
  deleted: string[];
}

export interface ImportItem {
  key: string;
  status: "new" | "changed" | "unchanged";
  visibility: Visibility;
}

export interface ImportResult {
  revision: number;
  dry_run: boolean;
  items: ImportItem[];
}

export interface DotenvError {
  line: number;
  code: string;
  message: string;
}
