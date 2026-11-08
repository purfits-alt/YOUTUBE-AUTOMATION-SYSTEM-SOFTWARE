import { defineConfig, devices } from "@playwright/test";
import { STORAGE_STATE } from "./tests/e2e/global-setup";

// The API serves the built SPA on 127.0.0.1:8765 with a migrated database, a master key and an
// owner account (see the CI web job). Auth, controls, settings and audit are real; other page data
// still comes from MSW mock handlers running in the page.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  fullyParallel: true,
  globalSetup: "./tests/e2e/global-setup.ts",
  expect: {
    // Visual snapshots: the bundled Inter font keeps text identical across machines; allow tiny AA noise.
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled", caret: "hide" },
  },
  use: {
    baseURL: process.env.TUBEFORGE_E2E_URL ?? "http://127.0.0.1:8765",
    trace: "off",
    storageState: STORAGE_STATE,
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
      : {}),
  },
  projects: [
    { name: "desktop", testIgnore: /(mobile|stateful)\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    // FRONTEND_SPECIFICATION §32 / roadmap: mobile layout checked at 390×844.
    {
      name: "mobile",
      testMatch: /(mobile|smoke)\.spec\.ts/,
      use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } },
    },
    // Tests that change shared server state (Emergency Stop, sign-out) run after everything else,
    // so no other test or screenshot sees their effects.
    {
      name: "stateful",
      testMatch: /stateful\.spec\.ts/,
      dependencies: ["desktop", "mobile"],
      fullyParallel: false,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
