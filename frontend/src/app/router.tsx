import { createBrowserRouter } from "react-router";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { OrganizationPage } from "../features/organizations/OrganizationPage";
import { OrganizationsPage } from "../features/organizations/OrganizationsPage";
import { ProjectPage } from "../features/projects/ProjectPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { AppShell } from "./AppShell";
import { NotFound } from "./NotFound";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <OrganizationsPage /> },
      { path: "orgs/:orgId", element: <OrganizationPage /> },
      { path: "orgs/:orgId/projects/:projectId", element: <ProjectPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
