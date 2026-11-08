import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { OWNER_EMAIL, OWNER_PASSWORD } from "./global-setup";
import { watchConsole } from "./helpers";

// These tests change shared server state; the "stateful" project runs them last and in order.
test.describe.configure({ mode: "serial" });

test("Emergency Stop: two clicks to stop, broadcast to other tabs, clearing asks for the password", async ({
  page,
  context,
}) => {
  // 403 = the API asking for step-up re-authentication before clearing (expected).
  const problems = watchConsole(page, [403]);
  const other = await context.newPage();
  await other.goto("/renders");
  await expect(other.getByTestId("state-success")).toBeVisible();

  await page.goto("/approvals");
  const stop = page.getByTestId("emergency-stop");
  await stop.click();
  const dialog = page.getByTestId("estop-dialog");
  await dialog.getByLabel("Reason (optional)").fill("e2e");
  await dialog.getByRole("button", { name: "Stop everything" }).click();
  await expect(stop).toHaveText(/STOPPED/);
  await expect(
    page.getByText("Emergency Stop is active — all automation is paused. Reason: e2e"),
  ).toBeVisible();
  // The other tab learns about it through the SSE stream, without reloading.
  await expect(other.getByText(/all automation is paused/)).toBeVisible();

  await stop.click();
  await page.getByTestId("estop-clear-dialog").getByRole("button", { name: "Resume" }).click();
  const reauth = page.getByTestId("reauth-modal");
  await reauth.getByLabel("Password").fill("not the password");
  await reauth.getByRole("button", { name: "Confirm" }).click();
  await expect(reauth.getByRole("alert")).toBeVisible();
  await reauth.getByLabel("Password").fill(OWNER_PASSWORD);
  await reauth.getByRole("button", { name: "Confirm" }).click();
  await expect(stop).toHaveText(/Emergency Stop/);
  await expect(page.getByText(/all automation is paused/)).toHaveCount(0);
  await expect(other.getByText(/all automation is paused/)).toHaveCount(0);
  expect(problems.filter((p) => !p.includes("status of 401"))).toEqual([]);
});

test("Audit & Security Center lists the actions and verifies the chain", async ({ page }) => {
  await page.goto("/security");
  await expect(page.getByTestId("state-success")).toBeVisible();
  await expect(page.getByText("system.emergency_stop_clear").first()).toBeVisible();
  await page.getByTestId("verify-chain").click();
  await expect(page.getByTestId("chain-result")).toContainText("rows intact");
});

test.describe("signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("sign-in screen: wrong password, then sign in and out", async ({ page }) => {
    // 401 = the wrong-password attempt and the initial "not signed in" check (expected).
    const problems = watchConsole(page, [401]);
    await page.goto("/");
    const form = page.getByTestId("login-form");
    await expect(form).toBeVisible();
    const a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(a11y.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);

    await form.getByLabel("E-mail").fill(OWNER_EMAIL);
    await form.getByLabel("Password").fill("definitely wrong");
    await form.getByRole("button", { name: "Sign in" }).click();
    await expect(form.getByRole("alert")).toContainText("not correct");
    await form.getByLabel("Password").fill(OWNER_PASSWORD);
    await form.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Overview Dashboard" })).toBeVisible();

    await page.getByTestId("sign-out").click();
    await expect(page.getByTestId("login-form")).toBeVisible();
    expect(problems).toEqual([]);
  });
});
