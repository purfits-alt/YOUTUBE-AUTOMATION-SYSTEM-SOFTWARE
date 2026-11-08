import { expect, test } from "@playwright/test";
import { watchConsole } from "./helpers";

test("Emergency Stop: two clicks to stop; clearing asks for the password", async ({ page }) => {
  // 403 = the API asking for step-up re-authentication before clearing (expected).
  const problems = watchConsole(page, [403]);
  await page.goto("/approvals");
  const stop = page.getByTestId("emergency-stop");
  await stop.click();
  const dialog = page.getByTestId("estop-dialog");
  await dialog.getByLabel("Reason (optional)").fill("demo");
  await dialog.getByRole("button", { name: "Stop everything" }).click();
  await expect(stop).toHaveText(/STOPPED/);
  await expect(
    page.getByText("Emergency Stop is active — all automation is paused. Reason: demo"),
  ).toBeVisible();
  // The banner stays on every page.
  await page.getByRole("link", { name: /Render Manager/ }).click();
  await expect(page.getByText(/all automation is paused/)).toBeVisible();

  await stop.click();
  await page.getByTestId("estop-clear-dialog").getByRole("button", { name: "Resume" }).click();
  const reauth = page.getByTestId("reauth-modal");
  await reauth.getByLabel("Password").fill("owner-password");
  await reauth.getByRole("button", { name: "Confirm" }).click();
  await expect(stop).toHaveText(/Emergency Stop/);
  await expect(page.getByText(/all automation is paused/)).toHaveCount(0);
  expect(problems).toEqual([]);
});

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
  await expect(links).toHaveCount(31);
  for (let i = 0; i < 31; i++) {
    const link = links.nth(i);
    const name = ((await link.textContent()) ?? "").replace(/^\d+/, "").trim();
    await link.click();
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  }
});
