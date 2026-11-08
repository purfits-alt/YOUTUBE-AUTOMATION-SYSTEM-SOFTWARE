import { delay, http, HttpResponse, type HttpHandler } from "msw";
import { API_BASE, type Problem } from "../lib/api/client";
import { getScenario } from "../lib/scenario";
import { PAGES, pageHref } from "../pages/registry";
import en from "../i18n/en.json";
import { overviewData, pageData, shellData } from "./data";

/** Mock backend state (resets on reload). */
const state = { estopActive: false, estopReason: null as string | null, stepUpUntil: 0 };

export function resetMockState(): void {
  state.estopActive = false;
  state.estopReason = null;
  state.stepUpUntil = 0;
}

function problem(status: number, code: string, title: string, detail: string): HttpResponse<Problem> {
  const body: Problem = {
    type: "about:blank",
    title,
    status,
    code,
    detail,
    request_id: "req-mock-" + code.toLowerCase(),
  };
  return HttpResponse.json(body, { status, headers: { "Content-Type": "application/problem+json" } });
}

/** Applies the dev scenario switcher; returns a response for loading/error, or null to continue. */
async function scenarioGate(): Promise<HttpResponse<Problem> | null> {
  const scenario = getScenario();
  if (scenario === "loading") {
    await delay("infinite");
  }
  if (scenario === "error") {
    return problem(
      503,
      "MOCK_ERROR",
      "Service unavailable",
      "The data service did not respond (simulated error).",
    );
  }
  await delay(120);
  return null;
}

const pageHandlers: HttpHandler[] = PAGES.filter((p) => p.id !== "overview").map((page) =>
  http.get(API_BASE + page.api.replace("{id}", ":id"), async () => {
    const gate = await scenarioGate();
    if (gate) return gate;
    return HttpResponse.json(pageData(page, getScenario() === "empty"));
  }),
);

export const handlers: HttpHandler[] = [
  http.get(API_BASE + "/dashboard/overview", async () => {
    const gate = await scenarioGate();
    if (gate) return gate;
    return HttpResponse.json(overviewData(getScenario() === "empty"));
  }),
  ...pageHandlers,
  http.get(API_BASE + "/shell", () => HttpResponse.json(shellData(state.estopActive, state.estopReason))),
  http.post(API_BASE + "/system/emergency-stop", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { reason?: string };
    state.estopActive = true;
    state.estopReason = body.reason?.trim() ? body.reason.trim() : null;
    return HttpResponse.json(shellData(state.estopActive, state.estopReason).controls);
  }),
  http.delete(API_BASE + "/system/emergency-stop", () => {
    if (Date.now() > state.stepUpUntil) {
      return problem(403, "REAUTH_REQUIRED", "Confirm it's you", "This action needs your password again.");
    }
    state.estopActive = false;
    state.estopReason = null;
    return HttpResponse.json(shellData(false, null).controls);
  }),
  http.post(API_BASE + "/auth/step-up", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { password?: string };
    // Mock: any non-empty password except "wrong" is accepted. Real step-up arrives in Phase 3.
    if (!body.password || body.password === "wrong") {
      return problem(401, "BAD_CREDENTIALS", "Not accepted", "That password was not accepted.");
    }
    state.stepUpUntil = Date.now() + 5 * 60_000;
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(API_BASE + "/search", ({ request }) => {
    const q = (new URL(request.url).searchParams.get("q") ?? "").trim().toLowerCase();
    if (!q) return HttpResponse.json([]);
    const pages = PAGES.filter((p) => en.pages[p.id].title.toLowerCase().includes(q)).map((p) => ({
      kind: "page",
      label: en.pages[p.id].title,
      href: pageHref(p),
    }));
    const entities = [
      { kind: "channel", label: "Calm Science", href: "/channels" },
      { kind: "channel", label: "Urdu Kahaniyan", href: "/channels" },
      { kind: "project", label: "Why octopuses dream", href: "/projects/p-101/script" },
      { kind: "idea", label: "The quiet maths of bridges", href: "/channels/ch-1/ideas" },
    ].filter((e) => e.label.toLowerCase().includes(q));
    return HttpResponse.json([...pages, ...entities].slice(0, 12));
  }),
];
