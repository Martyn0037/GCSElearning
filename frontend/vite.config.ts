// frontend/vite.config.ts
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API runs separately; proxying keeps requests same-origin,
// exactly as Caddy does in production, so cookies and CSRF behave identically.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: { sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/api/generated/**", "src/main.tsx", "src/test/**", "**/*.test.{ts,tsx}"],
      thresholds: { lines: 90, branches: 85, functions: 90, statements: 90 },
    },
  },
});
