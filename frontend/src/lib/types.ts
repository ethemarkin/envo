// Mirrors the backend response models (see /api/docs). To be replaced by
// types generated from the OpenAPI schema once the API surface settles.

export type Role = "owner" | "admin" | "developer" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string | null;
  email_verified: boolean;
  is_admin: boolean;
  has_password: boolean;
  providers: string[];
}

export interface Breadcrumb {
  id: string;
  name: string;
  slug: string;
}

export interface Group {
  id: string;
  parent_id: string | null;
  name: string;
  slug: string;
  path: string;
  description: string | null;
  role: Role;
  /** From the top-level group down to the parent. */
  ancestors: Breadcrumb[];
  created_at: string;
}

export interface Project {
  id: string;
  group_id: string | null;
  name: string;
  slug: string;
  path: string;
  description: string | null;
  role: Role;
  ancestors: Breadcrumb[];
  created_at: string;
  updated_at: string;
}

export interface GroupChild {
  id: string;
  type: "group" | "project";
  name: string;
  slug: string;
  description: string | null;
}

export interface TreeNode {
  id: string;
  /** Parent group id (for projects: their group), null at the root. */
  parent_id: string | null;
  name: string;
  slug: string;
  path: string;
  /** Null when the group is only shown as the path to something accessible. */
  role: Role | null;
}

export interface Tree {
  groups: TreeNode[];
  projects: TreeNode[];
  can_create_root: boolean;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  name: string | null;
  role: Role;
  created_at: string;
  inherited: boolean;
  source_type: "group" | "project";
  source_id: string;
  source_name: string;
}

export interface AdminUser {
  id: string;
  email: string;
  name: string | null;
  is_admin: boolean;
  created_at: string;
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
