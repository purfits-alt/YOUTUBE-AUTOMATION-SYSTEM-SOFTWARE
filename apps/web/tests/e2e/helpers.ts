import { expect, type Page } from "@playwright/test";
import en from "../../src/i18n/en.json" with { type: "json" };
import { PAGES, pageHref } from "../../src/pages/registry";
import type { PageDef } from "../../src/pages/types";

export { en, PAGES, pageHref };
export type { PageDef };

export const STATES = ["success", "empty", "loading", "error"] as const;
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
    const http = HTTP_LOG.exec(msg.text());
    if (http && expectedHttp.includes(Number(http[1]))) return;
    problems.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

export async function openPage(page: Page, def: PageDef, state: State = "success"): Promise<void> {
  await page.goto(`${pageHref(def)}?scenario=${state}`);
  await expect(page.getByRole("heading", { level: 1, name: en.pages[def.id].title })).toBeVisible();
}
