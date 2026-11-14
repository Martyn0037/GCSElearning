// frontend/src/app/routes.tsx
import type { RouteObject } from "react-router";

import { RequireRole } from "../auth/RequireRole";
import { LoginPage } from "../pages/LoginPage";
import { AdminHomePage, GuardianHomePage, StudentHomePage } from "../pages/HomePages";
import { NotFoundPage } from "../pages/NotFoundPage";

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
    path: "/guardian",
    element: (
      <RequireRole roles={["guardian"]}>{(user) => <GuardianHomePage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/admin",
    element: <RequireRole roles={["admin"]}>{(user) => <AdminHomePage user={user} />}</RequireRole>,
  },
  { path: "*", element: <NotFoundPage /> },
];
