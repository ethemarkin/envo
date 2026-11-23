import { ApiError } from "./api";

// Backend error codes → user-facing text.
const MESSAGES: Record<string, string> = {
  invalid_credentials: "Incorrect email or password.",
  invalid_current_password: "Current password is incorrect.",
  email_taken: "An account with this email already exists.",
  validation_error: "Please check the information you entered.",
  slug_taken: "This slug is already in use.",
  forbidden: "You don't have permission to do this.",
  csrf_failed: "Your session could not be verified. Refresh the page and try again.",
  not_authenticated: "Your session has expired. Please sign in again.",
  last_owner: "Every top-level group and project must keep at least one direct Owner.",
  group_not_found: "Group not found, or you don't have access to it.",
  root_creation_disabled:
    "On this instance, creating top-level groups or projects is restricted to admins. Create it inside a group or ask an admin.",
  user_not_found: "No user is registered with this email.",
  already_member: "This user is already a direct member.",
  member_not_found: "Membership not found.",
  admin_required: "Only admins can do this.",
  last_admin: "The instance must keep at least one admin.",
  invitation_not_found: "This invitation is invalid, expired, revoked or already used.",
  invitation_email_mismatch:
    "This invitation was sent to a different email address. Sign in with the address it was sent to.",
  invitation_required:
    "Accounts on this instance are invitation-only. Use the invitation link you received.",
  cannot_delete_self: "You can't delete your own account.",
  service_token_not_found: "Service token not found.",
  invalid_environment: "The selected environments don't belong to this project.",
  service_token_not_allowed: "Service tokens can't be used for this action.",
  revision_not_found: "Revision not found.",
  invalid_cursor: "The page link is invalid; refresh the list.",
  project_not_found: "Project not found, or you don't have access to it.",
  environment_not_found: "Environment not found.",
  revision_conflict:
    "Someone else changed this environment while you were editing. Load the latest version and reapply your changes.",
  invalid_dotenv: "The .env content has errors.",
  invalid_key: "Invalid key. Use letters, digits and underscores, and don't start with a digit.",
  duplicate_key: "The same key is defined more than once.",
  value_required: "New variables need a value.",
  variable_not_found: "Variable not found.",
  value_too_long: "Too long: variables can be up to 64 KB, config files up to 256 KB.",
  encryption_not_configured: "No encryption key is configured on the server.",
  cli_request_not_found:
    "No pending CLI sign-in found for this code. It may have expired; run envo login again in your terminal.",
  session_expired: "Your session has expired. Please sign in again.",
  invalid_path:
    "Invalid folder path. Use letters, digits, dots, hyphens and underscores in folder names, and separate subfolders with /.",
  folder_exists: "A folder already exists at this path.",
  folder_not_found: "Folder not found; refresh the page.",
  folder_into_itself: "A folder can't be moved into itself.",
  env_file_exists: "A .env already exists here.",
  env_file_not_found: ".env not found; refresh the page.",
  file_exists: "A file already exists at this path.",
  file_not_found: "File not found; refresh the page.",
  invalid_file_name:
    "Invalid file name. Use letters, digits, dots, hyphens and underscores (e.g. application.properties); .env files are added with “+ .env”.",
};

export function errorMessage(error: unknown): string {
  const code = error instanceof ApiError ? error.code : typeof error === "string" ? error : "";
  const message = MESSAGES[code] ?? "An unexpected error occurred.";
  const keys = error instanceof ApiError ? error.data.keys : undefined;
  return Array.isArray(keys) && keys.length > 0 ? `${message} (${keys.join(", ")})` : message;
}

export const ROLE_LABELS = {
  owner: "Owner",
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
} as const;
