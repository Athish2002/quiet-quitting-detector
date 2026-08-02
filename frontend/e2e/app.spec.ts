import { expect, test } from "@playwright/test";

// End-to-end against the real server and the real built bundle.
//
// The API key is supplied through the environment. There is no fixture that
// disables auth: an E2E suite that bypasses the security middleware would be
// testing an application nobody runs, and Phase 4 exists precisely because a
// route was reachable without a key.
const API_KEY = process.env.E2E_API_KEY ?? "";

test.beforeEach(async ({ page }) => {
  test.skip(!API_KEY, "E2E_API_KEY is not set");
  await page.addInitScript((key) => {
    sessionStorage.setItem("qqd.apiKey", key);
  }, API_KEY);
});

test("the shell loads and asks for a key when there is none", async ({
  page,
  context,
}) => {
  // The state a new operator arrives in: no key in session storage.
  //
  // This used to build its own context with `browser.newContext()` and close it
  // by hand. Two problems with that, and the second one bit: a manually created
  // context does NOT inherit `use.baseURL` from the config, and closing it
  // inside the test races the SPA's in-flight requests -- which showed up as an
  // intermittent failure at `context.close()`, the least informative place for
  // a test to fail.
  //
  // The managed fixture is torn down by Playwright after the test, so there is
  // nothing here to race. The init script below runs after the one in
  // beforeEach, so it wins.
  await context.addInitScript(() => {
    sessionStorage.removeItem("qqd.apiKey");
  });
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: /enter your api key/i }),
  ).toBeVisible();
});

test("home states what the system will not do", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Quiet-Quitting Detector" })).toBeVisible();
  await expect(page.getByText(/Rank people, or compare one person to another/i)).toBeVisible();
  await expect(page.getByText(/not a verdict about a person/i)).toBeVisible();
});

test("the diagnostic room reports calibration honestly", async ({ page }) => {
  await page.goto("/diagnostic");
  await expect(page.getByRole("heading", { name: /diagnostic room/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /is this system right/i })).toBeVisible();
  // Association, never causation -- the caveat must be on the page.
  await expect(page.getByText(/no control group/i)).toBeVisible();
});

test("the console lists the cohort and refuses to be a leaderboard", async ({
  page,
  request,
}) => {
  // Both assertions below are about how PEOPLE are presented, so both are
  // vacuous against an empty registry: the caption lives inside the table, and
  // "no sortable headers" passes trivially when there is no table. A fresh
  // checkout has an empty data/memory, which is precisely why this test passed
  // on a developer machine and failed on its first CI run.
  //
  // Seeded only when the registry is actually empty. POST /mock-data DELETES
  // every stored evaluation, and an E2E suite that destroys a developer's local
  // cohort to test a caption has done more damage than the test is worth.
  const headers = { Authorization: `Bearer ${API_KEY}` };
  const existing = await request.get("/api/v1/employees", { headers });
  if (((await existing.json()) as unknown[]).length === 0) {
    const seeded = await request.post("/api/v1/mock-data", { headers });
    expect(seeded.ok()).toBeTruthy();
  }

  await page.goto("/console");
  await expect(page.getByRole("heading", { name: "Console" })).toBeVisible();

  // There are rows, so the caption is rendered and the header check is real.
  await expect(page.getByRole("row").nth(1)).toBeVisible();
  await expect(page.getByText(/not a ranking/i)).toBeVisible();

  // No sortable column headers anywhere in the registry.
  const headerButtons = page.locator("th button");
  await expect(headerButtons).toHaveCount(0);
});

test("history separates the clearable log from the audit trail", async ({ page }) => {
  await page.goto("/history");
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  await expect(page.getByText(/cannot be cleared/i)).toBeVisible();
});

test("deep links and reloads work", async ({ page }) => {
  // The SPA uses history routing, so these paths are not files. Before the
  // fallback existed every one of them returned 401.
  for (const path of ["/console", "/history", "/diagnostic"]) {
    const response = await page.goto(path);
    expect(response?.status(), `${path} should serve the shell`).toBe(200);
    await expect(page.locator("main")).toBeVisible();
  }
});

test("keyboard users can skip to content", async ({ page }) => {
  await page.goto("/");
  // Tab until the skip link takes focus. Asserting it is reachable within the
  // first couple of stops is the property that matters -- the point of a skip
  // link is not having to tab through the nav, and an off-screen link that
  // never receives focus is worse than none because it looks handled.
  const skipLink = page.getByRole("link", { name: /skip to content/i });
  await expect(skipLink).toBeAttached();

  for (let stop = 0; stop < 3; stop += 1) {
    await page.keyboard.press("Tab");
    if (await skipLink.evaluate((el) => el === document.activeElement)) break;
  }
  await expect(skipLink).toBeFocused();

  // And it must actually become visible once focused, not stay off-screen.
  await expect(skipLink).toBeInViewport();
});

test("the API still refuses an unauthenticated request", async ({ request }) => {
  // The UI having a key must not mean the API is open.
  const response = await request.get("/api/v1/employees");
  expect(response.status()).toBe(401);
  expect(response.headers()["content-type"]).toContain("application/problem+json");
});

test("no inline script is permitted by the CSP", async ({ request }) => {
  const response = await request.get("/");
  const csp = response.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("script-src 'self'");
  expect(csp).not.toContain("script-src 'self' 'unsafe-inline'");
});
