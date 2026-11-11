/**
 * Answers for real pages whose data cannot exist in the e2e database (no worker runs there, so no
 * niche candidates, blueprints, trends or YouTube lookups are ever produced). Used by the
 * routes × states, axe and visual tests; the real flows are covered by the Python integration tests
 * and stateful.spec.ts. Shapes follow packages/shared/openapi.json.
 */
const NOW = "2026-11-10T06:00:00Z";
const FOOTER = "Estimates based on cited sources. Not a prediction of views, subscribers or earnings.";

const candidate = {
  id: "nc-1",
  report_id: "r-1",
  name: "Student budgets with real numbers",
  summary: "Explainers using the owner's own monthly budget.",
  language: "en",
  opportunity_score: "72.50",
  band: null,
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
  ],
  originality_angles: ["Share your own budget"],
  inauthentic_risk: "MEDIUM",
  production_difficulty: "LOW",
  status: "SHORTLISTED",
  footer: FOOTER,
};

const ideas = Array.from({ length: 50 }, (_, n) => ({
  title: `Idea number ${String(n + 1)}`,
  format: n % 3 === 0 ? "LONG" : "SHORT",
  pillar: "Budgeting basics",
  angle: "Own numbers",
}));

const strategy = {
  id: "st-1",
  niche_candidate_id: "nc-1",
  channel_id: null,
  version: 1,
  status: "PROPOSED",
  problems: [],
  approved_at: null,
  created_at: NOW,
  etag: "e1",
  blueprint: {
    schema_version: 1,
    niche: { candidate_id: "nc-1", name: "Student budgets with real numbers", language: "en" },
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
      contrast_pair: { text: "#F9FAFB", background: "#111827", ratio: 17.74 },
      fonts: [{ family: "Inter", use: "BODY", licence: "OFL-1.1" }],
      logo_brief: "Piggy bank made of a grid.",
      banner_brief: "Teal banner with a budget sheet.",
    },
    positioning: "A student who shows their real budget, mistakes included.",
    target_audience: { description: "University students", needs: ["Simple budgets"] },
    pillars: [{ name: "Budgeting basics", description: "Basics" }],
    formats: [
      { name: "Walk-through", format: "LONG", description: "Screen recording", owner_role: "voice" },
      { name: "Tip", format: "SHORT", description: "One tip", owner_role: "voice" },
      { name: "Q&A", format: "LONG", description: "Questions", owner_role: "on-camera" },
    ],
    calendar_30d: [
      { day: 1, idea_ref: 1, format: "SHORT" },
      { day: 2, idea_ref: 0, format: "LONG" },
    ],
    ideas,
    growth_strategy: ["Answer common questions in Shorts and link the long explainer."],
    risks: [
      { risk: "Templated slideshows may look inauthentic", severity: "HIGH", mitigation: "Own narration" },
    ],
    footer: FOOTER,
  },
};

const trend = {
  id: "t-1",
  channel_id: null,
  topic: "Rent rises for students",
  summary: "Several sources report rent increases this week.",
  signal_strength: "2.40",
  confidence: "MEDIUM",
  detected_at: NOW,
  expires_at: "2026-11-17T06:00:00Z",
  status: "ACTIVE",
  sources: [],
};

const lookup = {
  id: "l-1",
  kind: "CHANNEL",
  query_key: "handle:@budgetbros",
  items: [
    {
      type: "channel",
      title: "Budget Bros",
      channel_id: "UCabcdefghijklmnopqrstuv",
      video_id: null,
      handle: "@budgetbros",
      channel_title: null,
      published_at: "2020-01-01T00:00:00Z",
      duration: null,
      description_excerpt: "Budget videos for students.",
      subscriber_count: 12000,
      video_count: 90,
      view_count: 1500000,
    },
  ],
  cached: true,
  fetched_at: NOW,
  expires_at: "2026-12-10T06:00:00Z",
  notice: "Public info about one channel or video — not combined with others. Kept for 30 days at most.",
};

/** page id → (API pathname → JSON body) for the success state. */
export const SUCCESS_FIXTURES: Record<string, Record<string, unknown>> = {
  niche: { "/api/v1/niches/candidates/nc-1": candidate, "/api/v1/strategies": [strategy] },
  branding: { "/api/v1/strategies/st-1": strategy },
  trends: { "/api/v1/trends": [trend] },
  lookup: { "/api/v1/lookups/youtube": [lookup] },
};
