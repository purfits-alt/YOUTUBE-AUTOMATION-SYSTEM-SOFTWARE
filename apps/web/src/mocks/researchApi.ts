/**
 * Unit tests only: imitates the Phase 6 research endpoints (discovery, sources, lookups, trends,
 * blueprints). The browser talks to the real FastAPI backend; Python and e2e tests cover it.
 */
import { http, HttpResponse, type HttpHandler } from "msw";
import type {
  CandidateOut,
  LookupOut,
  ProfileOut,
  ReportDetail,
  SourceOut,
  StrategyOut,
  TrendOut,
} from "../lib/api/client";

const FOOTER = "Estimates based on cited sources. Not a prediction of views, subscribers or earnings.";
const NOW = "2026-11-10T06:00:00Z";

function candidate(overrides: Partial<CandidateOut> = {}): CandidateOut {
  return {
    id: "c-1",
    report_id: "r-1",
    name: "Student budgets with real numbers",
    summary: "Explainers using your own monthly budget.",
    language: "en",
    opportunity_score: "72.50",
    band: "10.0",
    criteria: [
      {
        code: "AUDIENCE_DEMAND",
        value: 70,
        weight: 8,
        confidence: "MEDIUM",
        evidence: [
          {
            source_document_id: "d-1",
            url: "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Budget/daily/2025111000/2026110900",
            title: "Pageviews · Budget · en.wikipedia",
            quote: "Average per day: 1200",
          },
        ],
        note: null,
      },
      {
        code: "PRODUCTION_FEASIBILITY",
        value: 90,
        weight: 9,
        confidence: "LOW",
        evidence: [],
        note: "Downgraded to LOW: no cited source document was found.",
      },
    ],
    originality_angles: ["Share your own budget"],
    inauthentic_risk: "MEDIUM",
    production_difficulty: "LOW",
    status: "NEW",
    remarks: [
      { kind: "STRENGTH", code: "AUDIENCE_DEMAND", value: 70, confidence: "MEDIUM" },
      { kind: "WATCH", code: "PRODUCTION_FEASIBILITY", value: 90, confidence: "LOW" },
    ],
    footer: FOOTER,
    ...overrides,
  };
}

function blueprint(): Record<string, unknown> {
  const ideas = Array.from({ length: 50 }, (_, n) => ({
    title: `Idea number ${String(n + 1)}`,
    format: n % 3 === 0 ? "LONG" : "SHORT",
    pillar: "Budgeting basics",
    angle: "Own numbers",
  }));
  return {
    schema_version: 1,
    niche: { candidate_id: "c-1", name: "Student budgets with real numbers", language: "en" },
    name_ideas: Array.from({ length: 10 }, (_, n) => ({
      name: `Budget Lab ${String(n + 1)}`,
      reason: "Clear topic",
      availability_note: "Check availability on YouTube, social platforms and trademarks manually",
    })),
    description: "Real student budgets, explained simply.",
    brand: {
      tone: ["calm", "practical"],
      palette: [
        { hex: "#0F766E", role: "primary" },
        { hex: "#111827", role: "dark" },
        { hex: "#F9FAFB", role: "light" },
        { hex: "#FDE68A", role: "accent" },
      ],
      contrast_pair: { text: "#F9FAFB", background: "#111827", ratio: 17.7 },
      fonts: [{ family: "Inter", use: "BODY", licence: "OFL-1.1" }],
      logo_brief: "Piggy bank made of a grid.",
      banner_brief: "Teal banner.",
    },
    positioning: "A student who shows their real budget.",
    target_audience: { description: "Students", needs: ["Simple budgets"] },
    pillars: [{ name: "Budgeting basics", description: "Basics" }],
    formats: [
      { name: "Walk-through", format: "LONG", description: "Screen", owner_role: "voice" },
      { name: "Tip", format: "SHORT", description: "One tip", owner_role: "voice" },
      { name: "Q&A", format: "LONG", description: "Questions", owner_role: "on-camera" },
    ],
    calendar_30d: [{ day: 2, idea_ref: 0, format: "LONG" }],
    ideas,
    growth_strategy: ["Answer questions in Shorts."],
    risks: [{ risk: "Templated slideshows", severity: "HIGH", mitigation: "Own narration" }],
    footer: FOOTER,
  };
}

interface ResearchState {
  report: ReportDetail;
  profiles: ProfileOut[];
  sources: SourceOut[];
  lookups: LookupOut[];
  trends: TrendOut[];
  strategy: StrategyOut;
  approvedChannel: string | null;
}

function initial(): ResearchState {
  return {
    report: {
      id: "r-1",
      status: "DONE",
      languages: ["en"],
      interests: [],
      avoid: [],
      weight_profile_id: null,
      documents: 23,
      candidates: 1,
      dropped: ["Side hustles: forbidden phrase 'guaranteed'"],
      skipped: [],
      error: null,
      created_at: NOW,
      updated_at: NOW,
      candidates_list: [candidate()],
    },
    profiles: [
      { id: "p-1", name: "Balanced", weights: { AUDIENCE_DEMAND: 8 }, is_default: true, max_weight: 15 },
      {
        id: "p-2",
        name: "Originality-first",
        weights: { AUDIENCE_DEMAND: 8 },
        is_default: false,
        max_weight: 15,
      },
    ],
    sources: [
      {
        id: "s-1",
        code: "WIKIPEDIA_PAGEVIEWS",
        kind: "API",
        base_url: "https://wikimedia.org/api/rest_v1/metrics/pageviews",
        allowed_hosts: ["wikimedia.org"],
        terms_url: "https://www.mediawiki.org/wiki/Wikimedia_REST_API#Terms_and_conditions",
        terms_verified_at: null,
        approval_status: "APPROVED",
        enabled: true,
        fetchable: true,
        documents: 0,
      },
    ],
    lookups: [],
    trends: [
      {
        id: "t-1",
        channel_id: "ch-1",
        topic: "Rent rises for students",
        summary: "Pageviews rose this week.",
        signal_strength: "2.40",
        confidence: "MEDIUM",
        detected_at: NOW,
        expires_at: "2026-11-17T06:00:00Z",
        status: "ACTIVE",
        sources: [],
      },
    ],
    strategy: {
      id: "st-9",
      niche_candidate_id: "c-1",
      channel_id: null,
      version: 1,
      status: "DRAFT",
      blueprint: blueprint(),
      problems: [],
      approved_at: null,
      created_at: NOW,
      etag: "e1",
    },
    approvedChannel: null,
  };
}

export let research = initial();

export function resetResearchApi(): void {
  research = initial();
}

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { title: code, status, code, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );

export const researchHandlers: HttpHandler[] = [
  http.get("/api/v1/niches/reports", () => HttpResponse.json([research.report])),
  http.post("/api/v1/niches/reports", () =>
    HttpResponse.json({ ...research.report, status: "QUEUED" }, { status: 202 }),
  ),
  http.get("/api/v1/niches/reports/:id", () => HttpResponse.json(research.report)),
  http.get("/api/v1/niches/candidates/:id", () => HttpResponse.json(research.report.candidates_list[0])),
  http.post("/api/v1/niches/candidates/:id/commands/:cmd", ({ params }) => {
    const status = params.cmd === "shortlist" ? "SHORTLISTED" : "DISMISSED";
    research.report.candidates_list = research.report.candidates_list.map((c) => ({ ...c, status }));
    return HttpResponse.json(research.report.candidates_list[0]);
  }),
  http.post("/api/v1/niches/rescore", () => HttpResponse.json(research.report.candidates_list)),
  http.get("/api/v1/niches/weight-profiles", () => HttpResponse.json(research.profiles)),
  http.post("/api/v1/strategies", () => HttpResponse.json({ job_id: 7, status: "QUEUED" }, { status: 202 })),
  http.get("/api/v1/strategies", () => HttpResponse.json([research.strategy])),
  http.get("/api/v1/strategies/:id", () => HttpResponse.json(research.strategy)),
  http.patch("/api/v1/strategies/:id", async ({ request }) => {
    if (request.headers.get("If-Match") !== `"${research.strategy.etag}"`)
      return problem(412, "VERSION_CONFLICT", "Reload");
    const body = (await request.json()) as { blueprint: Record<string, unknown> };
    research.strategy = { ...research.strategy, blueprint: body.blueprint, etag: "e2" };
    return HttpResponse.json(research.strategy);
  }),
  http.post("/api/v1/strategies/:id/commands/:cmd", async ({ params, request }) => {
    if (params.cmd === "propose") research.strategy = { ...research.strategy, status: "PROPOSED" };
    if (params.cmd === "approve") {
      const body = (await request.json()) as { channel_name: string };
      research.approvedChannel = body.channel_name;
      research.strategy = { ...research.strategy, status: "APPROVED", channel_id: "ch-1" };
    }
    return HttpResponse.json(research.strategy);
  }),
  http.get("/api/v1/research-sources", () => HttpResponse.json(research.sources)),
  http.patch("/api/v1/research-sources/:id", async ({ request }) => {
    const body = (await request.json()) as { terms_verified?: boolean; enabled?: boolean };
    research.sources = research.sources.map((s) => ({
      ...s,
      ...(body.terms_verified ? { terms_verified_at: "2026-11-10" } : {}),
      ...(body.enabled !== undefined ? { enabled: body.enabled } : {}),
    }));
    return HttpResponse.json(research.sources[0]);
  }),
  http.post("/api/v1/research-sources/:id/test", () =>
    HttpResponse.json({ documents_stored: 1, samples: [] }),
  ),
  http.get("/api/v1/lookups/youtube", () => HttpResponse.json(research.lookups)),
  http.post("/api/v1/lookups/youtube", async ({ request }) => {
    const body = (await request.json()) as { kind: LookupOut["kind"]; query: string };
    const out: LookupOut = {
      id: "l-1",
      kind: body.kind,
      query_key: `handle:${body.query.toLowerCase()}`,
      items: [
        {
          type: "channel",
          title: "Budget Bros",
          channel_id: "UCabcdefghijklmnopqrstuv",
          handle: "@budgetbros",
          published_at: "2020-01-01T00:00:00Z",
          description_excerpt: "Budget videos",
          subscriber_count: 12000,
          video_count: 90,
          view_count: 1500000,
        },
      ],
      cached: false,
      fetched_at: NOW,
      expires_at: "2026-12-10T06:00:00Z",
      notice: "Public info about one channel or video — not combined with others. Kept for 30 days at most.",
    };
    research.lookups = [out, ...research.lookups];
    return HttpResponse.json(out);
  }),
  http.get("/api/v1/trends", () => HttpResponse.json(research.trends.filter((x) => x.status === "ACTIVE"))),
  http.post("/api/v1/trends/:id/commands/:cmd", ({ params }) => {
    if (params.cmd === "to-idea") return problem(409, "NOT_AVAILABLE_YET", "Phase 7");
    research.trends = research.trends.map((x) => ({ ...x, status: "DISMISSED" }));
    return HttpResponse.json(research.trends[0]);
  }),
  http.post("/api/v1/trends/scan", () => HttpResponse.json({ job_id: 9, status: "QUEUED" }, { status: 202 })),
];
