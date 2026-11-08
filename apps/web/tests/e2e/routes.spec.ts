import { expect, test } from "@playwright/test";
import { en, openPage, PAGES, STATES, watchConsole } from "./helpers";

// Roadmap Phase 2: 31 routes × 4 states = 124 cases, no console errors, Emergency Stop on every route.
for (const def of PAGES) {
  test.describe(`${String(def.num).padStart(2, "0")} ${en.pages[def.id].title}`, () => {
    for (const state of STATES) {
      test(state, async ({ page }) => {
        const problems = watchConsole(page, state === "error" ? [503] : []);
        await openPage(page, def, state);
        await expect(page.getByTestId("emergency-stop")).toBeVisible();
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
