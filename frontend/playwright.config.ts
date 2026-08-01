import { defineConfig, devices } from "@playwright/test";

// E2E runs against the FastAPI server serving the BUILT bundle, not the Vite
// dev server. That is the configuration that actually ships, and it is the only
// one that exercises the pieces most likely to break in production: the SPA
// history fallback, the security middleware, and the CSP. A dev-server E2E
// would have passed happily while every deep link 401'd.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  // The backend is a Python process that imports the ADK stack lazily, so the
  // first request on a cold start is genuinely slow. Five seconds (the default)
  // made the FIRST test in the file fail roughly one run in three -- which is
  // the worst kind of flake, because it looks like whichever test happens to be
  // first is broken.
  expect: { timeout: 15_000 },
  timeout: 45_000,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
