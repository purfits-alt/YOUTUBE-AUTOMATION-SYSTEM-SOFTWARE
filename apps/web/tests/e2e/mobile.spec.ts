import { expect, test } from "@playwright/test";
import { en, openPage, PAGES, watchConsole } from "./helpers";

// Roadmap Phase 2: mobile layout (390×844) usable for pages 1, 22 and 27.
for (const num of [1, 22, 27]) {
  const def = PAGES.find((p) => p.num === num);
  if (!def) throw new Error(`page ${String(num)} missing`);
  test(`page ${String(num)} ${en.pages[def.id].title} is usable on a phone`, async ({ page }) => {
    const problems = watchConsole(page);
    await openPage(page, def);
    await expect(page.getByTestId("state-success")).toBeVisible();
    await expect(page.getByTestId("emergency-stop")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Quick navigation" })).toBeVisible();
    // No horizontal page scroll (tables may scroll inside their own box).
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(problems).toEqual([]);
  });
}

test("bottom tab bar and More drawer reach every page", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Quick navigation" })
    .getByRole("link", { name: "Approvals" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Owner Approval Center" })).toBeVisible();
  await page.getByTestId("more-button").click();
  const drawer = page.getByTestId("nav-drawer");
  await expect(drawer.getByRole("link")).toHaveCount(31);
  await drawer.getByRole("link", { name: /Settings & Integrations/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Settings & Integrations" })).toBeVisible();
  await expect(drawer).not.toBeVisible();
});
