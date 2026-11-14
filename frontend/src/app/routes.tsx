// frontend/src/app/routes.tsx
import type { RouteObject } from "react-router";

import { AdminPage } from "../admin/AdminPage";
import { RequireRole } from "../auth/RequireRole";
import { GuardianHomePage } from "../pages/HomePages";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { LazyPracticePage } from "../practice/LazyPracticePage";
import { LazyMistakesPage, LazyProgressPage, LazyReviewPage } from "../progress/LazyPages";
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
    path: "/practice/:enrolmentId/:topicId",
    element: (
      <RequireRole roles={["student"]}>{(user) => <LazyPracticePage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/review",
    element: (
      <RequireRole roles={["student"]}>{(user) => <LazyReviewPage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/mistakes",
    element: (
      <RequireRole roles={["student"]}>{(user) => <LazyMistakesPage user={user} />}</RequireRole>
    ),
  },
  {
    path: "/progress/:enrolmentId",
    element: (
      <RequireRole roles={["student"]}>{(user) => <LazyProgressPage user={user} />}</RequireRole>
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
