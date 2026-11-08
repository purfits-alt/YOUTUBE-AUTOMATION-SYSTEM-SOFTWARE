import { expect, test } from "@playwright/test";
import { en, openPage, PAGES, STATES, watchConsole } from "./helpers";

// Roadmap Phase 2: every route (31 + Channel Trending = 32) × 4 states = 128 cases, no console errors, Emergency Stop on every route.
for (const def of PAGES) {
  test.describe(`${String(def.num).padStart(2, "0")} ${en.pages[def.id].title}`, () => {
    // Real pages: block the MSW service worker so Playwright can intercept their API calls (requests
    // forwarded by a service worker are invisible to page.route). Mock pages need the worker.
    test.use({ serviceWorkers: def.real ? "block" : "allow" });
    for (const state of STATES) {
      test(state, async ({ page }) => {
        const problems = watchConsole(page, state === "error" ? [503] : []);
        await openPage(page, def, state);
        await expect(page.getByTestId("emergency-stop")).toBeVisible();
        // Settings has no empty state (FRONTEND_SPECIFICATION §31: "Empty state: N/A") — an empty
        // response is not possible for it, so its "empty" case checks it still renders its form.
        const expected = def.id === "settings" && state === "empty" ? "success" : state;
        if (def.id === "settings" && state === "empty") {
          await expect(page.getByTestId(`state-${expected}`)).toBeVisible();
          expect(problems).toEqual([]);
          return;
        }
        await expect(page.getByTestId(`state-${state}`)).toBeVisible();
        if (state === "error") await expect(page.getByTestId("state-error")).toContainText("MOCK_ERROR");
        if (state === "empty")
          await expect(page.getByTestId("state-empty")).toContainText(en.pages[def.id].empty);
        if (def.projectScoped && state === "success")
          await expect(page.getByTestId("project-header")).toBeVisible();
        if (def.safety) await expect(page.getByTestId("safety-note")).toBeVisible();
        // Loading must show skeletons, never a blank page.
        if (state === "loading")
          await expect(page.getByTestId("state-loading")).toHaveAttribute("aria-busy", "true");
        expect(problems).toEqual([]);
      });
    }
  });
}
