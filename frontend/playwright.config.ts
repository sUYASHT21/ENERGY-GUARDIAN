import { defineConfig } from "@playwright/test";

/* End-to-end tests against a running stack (backend + frontend), e.g.
 *   docker compose up            -> E2E_BASE_URL=http://localhost:8080
 *   make dev (backend + vite)    -> default http://127.0.0.1:5173
 * They log in, drive the simulator through the UI and check backend-driven results. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
});
