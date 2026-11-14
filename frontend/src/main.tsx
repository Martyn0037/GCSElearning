// frontend/src/main.tsx
import "./styles.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { createQueryClient } from "./app/queryClient";
import { routes } from "./app/routes";

const container = document.getElementById("root");
if (!container) throw new Error("Root element #root not found");

const queryClient = createQueryClient();
const router = createBrowserRouter(routes);

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
