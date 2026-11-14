// frontend/src/app/routes.tsx
import type { RouteObject } from "react-router";

import { AdminPage } from "../admin/AdminPage";
import { RequireRole } from "../auth/RequireRole";
import { GuardianHomePage } from "../pages/HomePages";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { SetupPage } from "../setup/SetupPage";
import { StudentHomePage } from "../subjects/StudentHomePage";
import { TopicMapPage } from "../subjects/TopicMapPage";

/** All app routes. Kept separate from the router so tests can mount them in memory. */
export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireRole roles={["student"]}>{(user) => <StudentHomePage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/setup",
    element: <RequireRole roles={["student"]}>{(user) => <SetupPage user={user} />}</RequireRole>,
  },
  {
    path: "/subjects/:enrolmentId",
    element: (
      <RequireRole roles={["student"]}>{(user) => <TopicMapPage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/guardian",
    element: (
      <RequireRole roles={["guardian"]}>{(user) => <GuardianHomePage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/admin",
    element: <RequireRole roles={["admin"]}>{(user) => <AdminPage user={user} />}</RequireRole>,
  },
  { path: "*", element: <NotFoundPage /> },
];
