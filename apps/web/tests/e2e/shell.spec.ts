import { expect, test } from "@playwright/test";
import { seed, watchConsole } from "./helpers";

test("theme switch: dark and back to light", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("theme-select").first().selectOption("dark");
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByTestId("theme-select").first().selectOption("light");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
});

test("global search with Ctrl+K navigates", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("state-success")).toBeVisible();
  await page.keyboard.press("Control+k");
  const dialog = page.getByTestId("search-dialog");
  await dialog.getByRole("searchbox").fill("thumb");
  await dialog.getByRole("button", { name: /Thumbnail Creator/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Thumbnail Creator" })).toBeVisible();
});

test("scenario switcher changes the state of the current page", async ({ page }) => {
  await page.goto("/renders");
  await expect(page.getByTestId("state-success")).toBeVisible();
  await page.getByTestId("scenario-switcher").selectOption("error");
  await expect(page.getByTestId("state-error")).toBeVisible();
  await page.getByTestId("scenario-switcher").selectOption("empty");
  await expect(page.getByTestId("state-empty")).toBeVisible();
  await page.getByTestId("scenario-switcher").selectOption("success");
  await expect(page.getByTestId("state-success")).toBeVisible();
});

test("every sidebar link opens its page", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  const links = nav.getByRole("link");
  await expect(links).toHaveCount(33);
  for (let i = 0; i < 33; i++) {
    const link = links.nth(i);
    const name = ((await link.textContent()) ?? "").replace(/^\d+/, "").trim();
    await link.click();
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  }
});

// Regression (2026-11-16): with the browser mock worker on (as in production), an old Replicate
// mock answered instead of the real API and crashed the tab. Every tab must open without errors.
test("Channel Trending: every tab opens on the real API without errors", async ({ page }) => {
  const problems = watchConsole(page, [404]);
  await page.goto(`/channels/${seed().channelId}/trending`);
  await expect(page.getByRole("heading", { level: 1, name: "Channel Trending" })).toBeVisible();
  await page.getByRole("tab", { name: "Replicate / Milk" }).click();
  await expect(page.getByText("Your published videos")).toBeVisible();
  await page.getByRole("tab", { name: "New Ideas" }).click();
  await expect(page.getByRole("button", { name: "Generate ideas" }).first()).toBeVisible();
  await expect(page.getByTestId("route-error")).toHaveCount(0);
  expect(problems).toEqual([]);
});

// Owner request 2026-11-18 (ADR-0031): the production line opens on the real API.
test("Pipeline: the production line opens on the real API without errors", async ({ page }) => {
  const problems = watchConsole(page);
  await page.goto("/pipeline");
  await expect(page.getByRole("heading", { level: 1, name: "Pipeline" })).toBeVisible();
  await expect(page.getByTestId("station-research")).toBeVisible();
  await expect(page.getByTestId("station-storyboard")).toContainText("Phase 8");
  await expect(page.getByTestId("route-error")).toHaveCount(0);
  expect(problems).toEqual([]);
});
