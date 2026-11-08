import { defineConfig, devices } from "@playwright/test";

// E2E smoke: the API serves the built SPA on 127.0.0.1:8765 (started by the CI job or the developer).
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env.TUBEFORGE_E2E_URL ?? "http://127.0.0.1:8765",
    trace: "off",
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
      : {}),
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
