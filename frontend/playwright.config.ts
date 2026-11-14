// frontend/playwright.config.ts
// End-to-end tests against a running stack (docker compose up + seeded accounts).
// See e2e/README.md for how to run them.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the flows share one student account
  workers: 1,
  // Flows sign in more than once, and password hashing is deliberately slow.
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://localhost",
    ignoreHTTPSErrors: true, // Caddy's local certificate for "localhost"
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "mobile-chrome", use: { ...devices["Pixel 7"] } }],
});
