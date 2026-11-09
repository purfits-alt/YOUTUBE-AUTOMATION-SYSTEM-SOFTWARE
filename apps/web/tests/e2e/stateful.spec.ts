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

test("channel setup: add a channel, follow the steps, save the OAuth client, Connect with Google", async ({
  page,
}) => {
  // 400 = the forged callback below (expected).
  const problems = watchConsole(page, [400]);
  await page.goto("/channels");
  await expect(page.getByTestId("state-success")).toBeVisible();
  await page.getByRole("button", { name: "Add channel" }).click();
  const dialog = page.getByTestId("add-channel-dialog");
  await dialog.getByLabel(/Channel name/).fill("E2E Lab");
  await dialog.getByRole("button", { name: "Create and start setup" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Channel Onboarding" })).toBeVisible();
  await page.getByRole("button", { name: "Start setup" }).click();
  await expect(page.getByTestId(/^step-/)).toHaveCount(10);
  await expect(page.getByText("0 of 10 steps done")).toBeVisible();

  const phone = page.getByTestId("step-VERIFY_PHONE");
  await phone.getByRole("button", { name: "Mark step done" }).click();
  await expect(phone.getByRole("button", { name: "Undo" })).toBeVisible();

  const form = page.getByTestId("oauth-client-form");
  await form.getByLabel("Client ID").fill("123456789-e2etest.apps.googleusercontent.com");
  await form.getByLabel(/Client secret/).fill("e2e-not-a-real-secret");
  await form.getByRole("button", { name: "Save OAuth client" }).click();
  await expect(page.getByTestId("oauth-client-registered")).toBeVisible();

  // Google's consent page is not contacted: answer it here and check what TubeForge asked for.
  await page.route("https://accounts.google.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>Google</title><h1>consent</h1>" }),
  );
  await page.getByTestId("connect-google").click();
  await page.waitForURL(/accounts\.google\.com/);
  const url = new URL(page.url());
  expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  expect(url.searchParams.get("redirect_uri")).toBe("http://127.0.0.1:8765/oauth/callback");
  expect(url.searchParams.get("scope")?.split(" ").sort()).toEqual([
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
  ]);
  expect(url.searchParams.get("state")).toHaveLength(43);

  // A forged redirect (unknown state) is refused and nothing is connected.
  await page.goto(`/oauth/callback?state=${"x".repeat(43)}&code=forged`);
  await expect(page.getByRole("heading", { name: "Not connected" })).toBeVisible();
  expect(problems).toEqual([]);
});

test("the bell shows real notifications and clears when read", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("bell-count")).toBeVisible();
  await page.getByTestId("notification-bell").click();
  await expect(page.getByRole("heading", { level: 1, name: "Notification Center" })).toBeVisible();
  await expect(page.getByTestId("notification").first()).toContainText("Upload stopped by a safety check");
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(page.getByTestId("bell-count")).toHaveCount(0);
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
