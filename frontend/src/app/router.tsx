import { createBrowserRouter } from "react-router";
import { GroupAuditPage, InstanceAuditPage, ProjectAuditPage } from "../features/audit/AuditPages";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { CliAuthorizePage } from "../features/cli/CliAuthorizePage";
import { InvitePage } from "../features/invitations/InvitePage";
import { EnvironmentPage } from "../features/environments/EnvironmentPage";
import { GroupPage } from "../features/navigation/GroupPage";
import { HomePage } from "../features/navigation/HomePage";
import { NewPage } from "../features/navigation/NewPage";
import { ProjectPage } from "../features/projects/ProjectPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { AppShell } from "./AppShell";
import { NotFound } from "./NotFound";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/invite/:token", element: <InvitePage /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "new", element: <NewPage /> },
      { path: "groups/:groupId", element: <GroupPage /> },
      { path: "projects/:projectId", element: <ProjectPage /> },
      { path: "projects/:projectId/audit", element: <ProjectAuditPage /> },
      { path: "groups/:groupId/audit", element: <GroupAuditPage /> },
      { path: "admin/audit", element: <InstanceAuditPage /> },
      { path: "projects/:projectId/environments/:envId", element: <EnvironmentPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "cli/authorize", element: <CliAuthorizePage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
