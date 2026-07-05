import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config. Tests run against the production Next.js build.
 *
 * Playwright manages the Next.js server (build + start) via `webServer`.
 * The Django GraphQL backend must already be running on :8000 — in CI the
 * workflow starts it; locally, run `python manage.py runserver` first.
 */
// Port is overridable (E2E_PORT) so a local run can avoid a dev server already
// on :3000. CI leaves it at the default 3000.
const PORT = process.env.E2E_PORT ?? "3000";
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }]]
    : "html",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: `npm run build && npm run start -- -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
