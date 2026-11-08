import { defineConfig, devices } from "@playwright/test";

// The API serves the built SPA on 127.0.0.1:8765 (started by the CI job or the developer).
// Phase 2 data comes from MSW mock handlers running in the page.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  fullyParallel: true,
  expect: {
    // Visual snapshots: the bundled Inter font keeps text identical across machines; allow tiny AA noise.
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled", caret: "hide" },
  },
  use: {
    baseURL: process.env.TUBEFORGE_E2E_URL ?? "http://127.0.0.1:8765",
    trace: "off",
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
      : {}),
  },
  projects: [
    { name: "desktop", testIgnore: /mobile\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    // FRONTEND_SPECIFICATION §32 / roadmap: mobile layout checked at 390×844.
    {
      name: "mobile",
      testMatch: /(mobile|smoke)\.spec\.ts/,
      use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } },
    },
  ],
});
