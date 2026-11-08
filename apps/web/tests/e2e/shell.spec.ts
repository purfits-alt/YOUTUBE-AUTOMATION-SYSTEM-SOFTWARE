import { expect, test } from "@playwright/test";

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
  await expect(links).toHaveCount(32);
  for (let i = 0; i < 32; i++) {
    const link = links.nth(i);
    const name = ((await link.textContent()) ?? "").replace(/^\d+/, "").trim();
    await link.click();
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  }
});
