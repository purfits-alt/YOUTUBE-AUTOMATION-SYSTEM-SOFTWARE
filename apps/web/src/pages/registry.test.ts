import { describe, expect, it } from "vitest";
import stub from "../../../../packages/shared/openapi.stub.json";
import { hasKey } from "../i18n";
import { GROUP_ORDER, PAGES, pageHref } from "./registry";

describe("page registry", () => {
  it("has the 31 pages of FRONTEND_SPECIFICATION, numbered 1..31", () => {
    expect(PAGES).toHaveLength(31);
    expect(PAGES.map((p) => p.num).sort((a, b) => a - b)).toEqual(
      Array.from({ length: 31 }, (_, i) => i + 1),
    );
    expect(new Set(PAGES.map((p) => p.path)).size).toBe(31);
  });

  it("puts project pages 11–18 under /projects/:id and gives them the project header", () => {
    for (const p of PAGES) expect(p.projectScoped).toBe(p.num >= 11 && p.num <= 18);
  });

  it("has every text in en.json", () => {
    for (const p of PAGES) {
      for (const field of ["title", "purpose", "empty", "emptyAction"])
        expect(hasKey(`pages.${p.id}.${field}`)).toBe(true);
      for (const c of p.columns) expect(hasKey(`columns.${c}`)).toBe(true);
      for (const a of p.actions) expect(hasKey(`actions.${a}`)).toBe(true);
      expect(GROUP_ORDER).toContain(p.group);
    }
  });

  it("uses only endpoints declared in the OpenAPI stub", () => {
    const paths = Object.keys(stub.paths);
    for (const p of PAGES) expect(paths).toContain(p.api);
  });

  it("builds concrete links without route parameters", () => {
    for (const p of PAGES) expect(pageHref(p)).not.toContain(":");
  });
});
