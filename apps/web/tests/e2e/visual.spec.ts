import { expect, test } from "@playwright/test";

// Visual snapshots of key pages (roadmap Phase 2). Update with: pnpm -C apps/web e2e --update-snapshots
const KEY_PAGES = [
  ["overview", "/"],
  ["approvals", "/approvals"],
  ["script", "/projects/p-101/script"],
  ["discovery", "/discovery"],
] as const;

for (const scheme of ["light", "dark"] as const) {
  test.describe(scheme, () => {
    // Reduced motion: count-ups, chart drawing and Lottie show their final frame, so pixels are stable.
    test.use({ colorScheme: scheme, reducedMotion: "reduce", viewport: { width: 1366, height: 900 } });
    for (const [name, url] of KEY_PAGES) {
      test(name, async ({ page }) => {
        await page.goto(url);
        await expect(page.getByTestId("state-success")).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await expect(page).toHaveScreenshot(`${name}-${scheme}.png`, { fullPage: true });
      });
    }
  });
}
