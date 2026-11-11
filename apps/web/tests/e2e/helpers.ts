import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";
import { SUCCESS_FIXTURES } from "./fixtures";
import { SEED_FILE } from "./global-setup";
import en from "../../src/i18n/en.json" with { type: "json" };
import { PAGES, pageHref } from "../../src/pages/registry";
import type { PageDef } from "../../src/pages/types";

export { en, PAGES, pageHref };
export type { PageDef };

export const STATES = ["success", "empty", "loading", "error"] as const;

/** IDs of the real data created by global-setup. */
export function seed(): { channelId: string } {
  return JSON.parse(readFileSync(SEED_FILE, "utf-8")) as { channelId: string };
}

/** Real pages whose main endpoint returns a plain array (not a cursor page). */
const ARRAY_PAGES = new Set(["agents", "usage", "discovery", "trends", "lookup"]);

/** Pages with no empty state (FRONTEND_SPECIFICATION: "Empty state: N/A" / steps always exist). */
export const NO_EMPTY_STATE = new Set(["settings", "onboarding", "niche", "branding"]);

/** URL of a page: real channel pages open the seeded channel, mock pages keep the sample IDs. */
export function hrefFor(def: PageDef): string {
  return def.real ? pageHref(def, seed().channelId) : pageHref(def);
}
export type State = (typeof STATES)[number];

const HTTP_LOG = /Failed to load resource: the server responded with a status of (\d+)/;

/**
 * Collects console errors/warnings and uncaught exceptions; assert it stays empty.
 * `expectedHttp`: statuses the test provokes on purpose (the browser logs those as errors itself).
 */
export function watchConsole(page: Page, expectedHttp: readonly number[] = []): string[] {
  const problems: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error" && msg.type() !== "warning") return;
    // Printed by Playwright itself when a test blocks service workers (real-page tests).
    if (msg.text() === "Service Worker registration blocked by Playwright") return;
    const http = HTTP_LOG.exec(msg.text());
    if (http && expectedHttp.includes(Number(http[1]))) return;
    problems.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

/**
 * Real pages (Security, Settings) are backed by the API, so their empty/loading/error states are
 * produced by intercepting the page's main request; mock pages use the MSW scenario switch.
 */
const SHELL_STUB = {
  channels: [{ id: "ch-1", name: "Calm Science", mode: "MANUAL", private_only: true, token_expiring: false }],
  quota: { youtube_default_pct: 17, free_tier_peak_pct: 41 },
  unread_notifications: 2,
};

/** The id in a real page's main API path: the seeded channel, or the sample id in the page URL. */
function apiId(def: PageDef): string {
  if (def.path.startsWith("/channels/")) return seed().channelId;
  return hrefFor(def).split("/").pop() ?? "";
}

async function interceptRealPage(page: Page, def: PageDef, state: State): Promise<void> {
  if (!def.real) return;
  // These tests block the MSW service worker (see routes.spec.ts), so answer its one mocked call here.
  await page.route(
    (url) => url.pathname === "/api/v1/shell",
    (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SHELL_STUB) }),
  );
  const fixtures = SUCCESS_FIXTURES[def.id];
  const showsData = state === "success" || (NO_EMPTY_STATE.has(def.id) && state === "empty");
  if (fixtures && showsData) {
    await page.route(
      (url) => url.pathname in fixtures,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(fixtures[new URL(route.request().url()).pathname]),
        }),
    );
    return;
  }
  if (showsData) return;
  const path = `/api/v1${def.api.replace("{id}", apiId(def))}`;
  await page.route(
    (url) => url.pathname === path,
    async (route) => {
      if (state === "loading") return; // never answer → skeleton stays
      if (state === "error") {
        await route.fulfill({
          status: 503,
          contentType: "application/problem+json",
          body: JSON.stringify({
            title: "Service unavailable",
            status: 503,
            code: "MOCK_ERROR",
            detail: "Simulated.",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        // List endpoints of the Phase 5 pages return arrays; the others return a page.
        body: JSON.stringify(ARRAY_PAGES.has(def.id) ? [] : { items: [], next_cursor: null }),
      });
    },
  );
}

export async function openPage(page: Page, def: PageDef, state: State = "success"): Promise<void> {
  await interceptRealPage(page, def, state);
  await page.goto(`${hrefFor(def)}?scenario=${state}`);
  await expect(page.getByRole("heading", { level: 1, name: en.pages[def.id].title })).toBeVisible();
}
