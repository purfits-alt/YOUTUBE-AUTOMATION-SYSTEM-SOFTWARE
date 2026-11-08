import { expect, test } from "@playwright/test";

test("dashboard loads with the shell and mocked data", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview Dashboard" })).toBeVisible();
  await expect(page.getByTestId("emergency-stop")).toBeVisible();
  await expect(page.getByTestId("state-success")).toBeVisible();
});

test("healthz responds", async ({ request }) => {
  const res = await request.get("/healthz");
  expect(res.ok()).toBeTruthy();
  expect((await res.json()).status).toBe("ok");
});
