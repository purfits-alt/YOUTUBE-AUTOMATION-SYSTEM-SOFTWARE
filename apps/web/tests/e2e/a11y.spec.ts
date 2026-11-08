import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { en, openPage, PAGES } from "./helpers";

// Roadmap Phase 2: axe per route, 0 serious/critical violations (WCAG 2.2 AA tags), light and dark.
for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe (${scheme})`, () => {
    // Reduced motion: measure the final page, not a card halfway through its 0.4 s fade-in
    // (mid-fade opacity would be reported as low contrast).
    test.use({ colorScheme: scheme, reducedMotion: "reduce" });
    for (const def of PAGES) {
      test(`${String(def.num).padStart(2, "0")} ${en.pages[def.id].title}`, async ({ page }) => {
        await openPage(page, def);
        await expect(page.getByTestId("state-success")).toBeVisible();
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
          .analyze();
        const serious = results.violations
          .filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
        expect(serious).toEqual([]);
      });
    }
  });
}
