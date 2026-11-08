import { expect, test } from "@playwright/test";

test("dashboard placeholder loads and reaches the backend", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TubeForge is running" })).toBeVisible();
  await expect(page.getByTestId("backend-ok")).toContainText("ok");
});

test("healthz responds", async ({ request }) => {
  const res = await request.get("/healthz");
  expect(res.ok()).toBeTruthy();
  expect((await res.json()).status).toBe("ok");
});
