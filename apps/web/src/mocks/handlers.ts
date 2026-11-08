import { delay, http, HttpResponse, type HttpHandler } from "msw";
import { API_BASE, type Problem } from "../lib/api/client";
import { getScenario } from "../lib/scenario";
import { PAGES, pageHref } from "../pages/registry";
import en from "../i18n/en.json";
import { overviewData, pageData, replicateData, shellData } from "./data";

/** Mock similarity of a variation to its source, per kind (the real check is A08 + embeddings, Phase 7). */
const VARIATION_SIMILARITY: Record<string, number> = {
  PART_2: 0.55,
  NEW_ANGLE: 0.42,
  UPDATE: 0.78,
  SHORT_FROM_LONG: 0.64,
  LONG_FROM_SHORT: 0.48,
  SERIES: 0.36,
};
export const REPLICATE_THRESHOLD = 0.7;

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

/** Pages still on mock data (Overview has its own handler; Security and Settings are real since Phase 3). */
const pageHandlers: HttpHandler[] = PAGES.filter((p) => !p.real && p.id !== "overview").map((page) =>
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
  http.get(API_BASE + "/shell", () => HttpResponse.json(shellData())),
  http.get(API_BASE + "/channels/:id/replicate", async () => {
    const gate = await scenarioGate();
    if (gate) return gate;
    return HttpResponse.json(replicateData(getScenario() === "empty"));
  }),
  http.post(API_BASE + "/channels/:id/ideas/replicate", async ({ request }) => {
    const body = (await request.json()) as { youtube_video_id: string; kind: string; note?: string };
    const similarity = VARIATION_SIMILARITY[body.kind] ?? 0.5;
    if (similarity > REPLICATE_THRESHOLD) {
      return problem(422, "TOO_SIMILAR", "Too similar", "The variation is too close to the original video.");
    }
    return HttpResponse.json({
      idea_title: `Variation (${body.kind.toLowerCase().replace(/_/g, " ")})`,
      similarity_to_source: similarity,
      threshold: REPLICATE_THRESHOLD,
    });
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
