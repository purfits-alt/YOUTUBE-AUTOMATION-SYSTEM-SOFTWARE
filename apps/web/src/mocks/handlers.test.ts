import { describe, expect, it } from "vitest";
import contract from "../../../../packages/shared/openapi.json";
import { PAGES } from "../pages/registry";
import { handlers } from "./handlers";

/** Path patterns as "/api/v1/a/{}/b" so MSW (":id") and OpenAPI ("{x}") forms compare. */
const norm = (p: string) => p.replace(/:[^/]+/g, "{}").replace(/\{[^}]+\}/g, "{}");

describe("browser mocks never answer for the real API", () => {
  it("only still-mocked pages (and the overview, shell and search) have browser handlers", () => {
    const real = new Set(Object.keys(contract.paths).map(norm));
    // A page still on sample data may mock its own path even where the API already has one.
    const mockedPages = new Set(PAGES.filter((p) => !p.real).map((p) => norm("/api/v1" + p.api)));
    const clashes = handlers
      .map((h) => norm(String((h.info as { path: unknown }).path)))
      .filter((path) => real.has(path) && !mockedPages.has(path));
    // Regression (2026-11-16): an old Replicate mock answered in place of the real API and broke the page.
    expect(clashes).toEqual([]);
  });
});
