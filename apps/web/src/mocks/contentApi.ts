/**
 * Unit tests and the public demo only: imitates the Phase 7 content endpoints (ideas, calendar,
 * Replicate, projects, research, claims, script versions). The app itself talks to the real
 * FastAPI backend; the Python integration tests cover the real behaviour.
 */
import { http, HttpResponse, type HttpHandler } from "msw";
import type { components } from "../lib/api/schema";
import type {
  BriefOut,
  ClaimOut,
  IdeaOut,
  ProjectOut,
  ReplicateOut,
  ValueAddOut,
  VersionOut,
  VersionSummaryOut,
} from "../lib/api/client";

const NOW = "2026-11-16T06:00:00Z";
const CHANNEL = "ch-1";
const PROJECT = "p-101";

function idea(overrides: Partial<IdeaOut>): IdeaOut {
  return {
    id: "i-1",
    channel_id: CHANNEL,
    state: "SUGGESTED",
    title: "I tested 5 free AI note apps for a week",
    angle: "Same notes, five apps, my own scores for speed and accuracy.",
    target_viewer: "Students",
    format: "LONG",
    pillar: "Free AI tools",
    trend_item_id: null,
    originality_notes: "My own week of tests",
    similarity_max: null,
    similar_to_id: null,
    similar_to_title: null,
    duplicate: false,
    maybe_same_idea: false,
    calendar_date: null,
    expires_at: null,
    source: "AGENT",
    based_on_youtube_video_id: null,
    variation_kind: null,
    similarity_to_source: null,
    packaging_promise: {
      title_idea: "I tested 5 free AI note apps",
      thumbnail_text_idea: "5 APPS, 1 WINNER",
      promise_statement: "See which free AI note app was fastest and most accurate in my own test.",
    },
    owner_value_add_prompt: "Which app did you keep using after the test, and why?",
    project_id: null,
    version: 1,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

const longScript = {
  promise_delivery: {
    promise_statement: "Which free AI note app won",
    delivered_at_s: 5,
    text: "I tested five free AI note apps for a week.",
  },
  hook: {
    text: "I gave five free AI note apps the same messy lecture notes for a week. One of them quietly rewrote half my facts. Another saved me an hour every single day.",
    est_s: 12,
    technique: ["COLD_OPEN_STORY", "STAKES"],
  },
  sections: [
    {
      heading: "The test",
      text: "Same notes, same week, five apps. [[OWNER: why you started the test]]",
      fact_refs: ["c1"],
      beat: "SETUP",
    },
    {
      heading: "The surprise",
      text: "The fastest app was not the most accurate one.",
      fact_refs: [],
      beat: "REVEAL",
    },
    { heading: "What I kept", text: "[[OWNER: the app you kept and why]]", fact_refs: [], beat: "PAYOFF" },
  ],
  re_hooks: [
    { at_pct: 25, technique: "PROGRESS_MARKER", text: "That's app one. App two looks better than it is." },
    { at_pct: 50, technique: "TWIST", text: "And here's where it got weird." },
    { at_pct: 75, technique: "OPEN_LOOP", text: "Before the winner, look at this number." },
  ],
  open_loops: [{ id: "L1", opened_in_section: 0, closed_in_section: 2, text: "Which app won" }],
  payoff: "The winner, and the one setting that made it accurate.",
  cta: "If you try it this week, tell me which app you kept.",
  owner_slots: [
    { section_index: 0, prompt: "Why you started" },
    { section_index: 2, prompt: "The app you kept" },
  ],
  est_duration_s: 470,
  word_count: 1175,
};

type JobProgressOut = components["schemas"]["JobProgressOut"];
type ChannelArtOut = components["schemas"]["ChannelArtOut"];
type ArtOut = components["schemas"]["ArtOut"];
type AssetOut = components["schemas"]["AssetOut"];

/** A small drawn picture for the demo and unit tests (the real art is a PNG from the worker). */
function svg(w: number, h: number, bg: string, text: string, size: number): string {
  const body =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${String(w)}" height="${String(h)}">` +
    `<rect width="100%" height="100%" fill="${bg}"/>` +
    `<text x="50%" y="50%" fill="#F8FAFC" font-family="sans-serif" font-weight="700" font-size="${String(size)}" text-anchor="middle" dominant-baseline="middle">${text}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(body)}`;
}

const STYLES = {
  LOGO: ["Monogram ring", "Gradient", "Badge"],
  BANNER: ["Bold centre", "Gradient left", "Band"],
};

function art(role: "LOGO" | "BANNER" | "WATERMARK", variant: number, batch: number): ArtOut {
  const [w, h] = role === "LOGO" ? [800, 800] : role === "BANNER" ? [2560, 1440] : [150, 150];
  const bg = ["#0F172A", "#14532D", "#1E3A8A"][(variant - 1) % 3] ?? "#0F172A";
  return {
    id: `art-${role.toLowerCase()}-${String(batch)}-${String(variant)}`,
    role,
    batch,
    variant,
    style: role === "WATERMARK" ? "Your logo" : (STYLES[role][variant - 1] ?? ""),
    chosen: role === "WATERMARK",
    asset_id: `asset-${role.toLowerCase()}-${String(batch)}-${String(variant)}`,
    width: w,
    height: h,
    size_bytes: 48000,
    text_contrast: 17.85,
    licence: "Drawn by TubeForge from your blueprint; font Source Sans Pro (SIL OFL 1.1)",
    download_url: svg(w, h, bg, role === "BANNER" ? "Calm Science" : "CS", role === "BANNER" ? 220 : 300),
    created_at: NOW,
  };
}

function withPicks(a: ChannelArtOut): ChannelArtOut {
  const all = [...a.logos, ...a.banners];
  return {
    ...a,
    chosen_logo: a.logos.find((x) => x.chosen) ?? a.chosen_logo,
    chosen_banner: a.banners.find((x) => x.chosen) ?? a.chosen_banner,
    logos: all.filter((x) => x.role === "LOGO"),
    banners: all.filter((x) => x.role === "BANNER"),
  };
}
type PipelineOut = components["schemas"]["PipelineOut"];
type BoardItem = components["schemas"]["BoardItemOut"];

type StationRow = [key: string, label: string, who: "TUBEFORGE" | "OWNER", phase: number, states: string[]];
const FIRST: StationRow = ["research", "Research", "TUBEFORGE", 7, ["IDEA", "RESEARCHING"]];
/** The production line (mirror of tubeforge.api.v1.pipeline.STATIONS). */
const STATIONS: StationRow[] = [
  FIRST,
  ["research_review", "Check the research", "OWNER", 7, ["RESEARCH_REVIEW"]],
  ["script", "Script writing", "TUBEFORGE", 7, ["SCRIPTING"]],
  ["script_review", "Approve the script", "OWNER", 7, ["SCRIPT_REVIEW"]],
  ["storyboard", "Storyboard", "TUBEFORGE", 8, ["STORYBOARDING"]],
  ["visuals", "Visuals", "TUBEFORGE", 8, ["ASSET_GENERATION"]],
  ["voice", "Voice-over", "TUBEFORGE", 8, ["VOICEOVER"]],
  ["edit", "Video edit", "TUBEFORGE", 9, ["ASSEMBLY"]],
  ["cut_review", "Check the rough cut", "OWNER", 9, ["ROUGH_CUT_REVIEW", "EXTERNAL_EDITING"]],
  ["render", "Render", "TUBEFORGE", 9, ["RENDERING"]],
  ["package", "Thumbnail & SEO", "TUBEFORGE", 10, ["PACKAGING"]],
  ["audit", "Quality & policy checks", "TUBEFORGE", 11, ["QC_AUDIT", "BLOCKED"]],
  ["approval", "Approve publishing", "OWNER", 12, ["READY_FOR_APPROVAL", "APPROVED"]],
  ["upload", "Upload", "TUBEFORGE", 12, ["UPLOADING", "PROCESSING", "SCHEDULED", "PRIVATE_DONE"]],
  ["analytics", "Analytics", "TUBEFORGE", 13, ["PUBLISHED", "ANALYZING", "ARCHIVED"]],
];

function station(i: number, count = 0) {
  const [key, label, who, phase] = STATIONS[i] ?? FIRST;
  return { key, label, who, phase, ready: phase <= 7, count };
}

/** GET /pipeline from the mock projects (the real rules live in the API, ADR-0031). */
export function pipelineOut(channelId?: string | null): PipelineOut {
  const counts = STATIONS.map(() => 0);
  const all = [content.project, content.researching].filter((p) => !channelId || p.channel_id === channelId);
  const projects = all.map((p) => {
    const index = Math.max(
      0,
      STATIONS.findIndex(([, , , , states]) => states.includes(p.state)),
    );
    counts[index] = (counts[index] ?? 0) + 1;
    const [, , who, phase] = STATIONS[index] ?? FIRST;
    const progress = p.progress ?? null;
    const activity: PipelineOut["projects"][number]["activity"] =
      phase > 7
        ? "NOT_BUILT"
        : who === "OWNER"
          ? "YOUR_TURN"
          : progress?.status === "RUNNING"
            ? "WORKING"
            : progress?.status === "FAILED"
              ? "STOPPED"
              : progress
                ? "QUEUED"
                : "STALLED";
    return {
      id: p.id,
      title: p.working_title,
      channel_id: p.channel_id,
      channel_name: "Calm Science",
      format: p.format,
      state: p.state,
      station: STATIONS[index]?.[0] ?? "research",
      activity,
      progress,
      next: index + 1 < STATIONS.length ? station(index + 1) : null,
      steps: STATIONS.map(([key], i) => ({
        key,
        status: i < index ? "done" : i === index ? "current" : i === index + 1 ? "next" : "later",
      })) as PipelineOut["projects"][number]["steps"],
      link: `/projects/${p.id}/script`,
      updated_at: p.updated_at,
    };
  });
  const busy = [content.researching.progress, ...content.jobs].some(
    (j) => j && (j.status === "RUNNING" || j.status === "QUEUED"),
  );
  // State board: the same buckets as tubeforge.api.v1.pipeline._board.
  const boards = STATIONS.map((_, i) => ({
    received_from: i > 0 ? (STATIONS[i - 1]?.[1] ?? null) : "Approved idea",
    forwards_to: STATIONS[i + 1]?.[1] ?? null,
    inbox: [] as BoardItem[],
    in_progress: [] as BoardItem[],
    attention: 0,
    complete: 0,
    forwarded: [] as BoardItem[],
  }));
  projects.forEach((item) => {
    const at = STATIONS.findIndex(([key]) => key === item.station);
    const entry: BoardItem = {
      id: item.id,
      title: item.title,
      activity: item.activity,
      pct: item.progress?.pct ?? null,
    };
    const card = boards[at];
    if (!card) return;
    if (["QUEUED", "YOUR_TURN", "NOT_BUILT", "PAUSED"].includes(item.activity)) card.inbox.push(entry);
    else card.in_progress.push(entry);
    boards.slice(0, at).forEach((b) => (b.complete += 1));
    boards[at - 1]?.forwarded.push(entry);
  });
  // A card per channel, counted over every channel's videos (the API does the same).
  const everyone = channelId ? pipelineOut(null).projects : projects;
  const card = (id: string, name: string, state: string) => {
    const mine = everyone.filter((p) => p.channel_id === id);
    const n = (a: string) => mine.filter((p) => p.activity === a).length;
    return {
      id,
      name,
      state,
      private_only: true,
      videos: mine.length,
      working: n("WORKING"),
      queued: n("QUEUED"),
      your_turn: n("YOUR_TURN"),
      attention: n("STALLED") + n("STOPPED") + n("WAITING") + n("BLOCKED"),
      next_phase: n("NOT_BUILT"),
      published: n("DONE"),
      paused: n("PAUSED"),
    };
  };
  return {
    channels: [card(CHANNEL, "Calm Science", "ACTIVE"), card("ch-2", "Urdu Kahaniyan", "ONBOARDING")],
    channel_id: channelId ?? null,
    stations: STATIONS.map((_, i) => ({ ...station(i, counts[i]), board: boards[i] ?? null })),
    projects,
    jobs: content.jobs,
    refresh_s: busy ? 3 : 20,
    built_phase: 7,
  };
}

interface ContentState {
  art: ChannelArtOut;
  artRequests: { tagline?: string | null }[];
  watermarkUploads: { type: string; confirmed: boolean }[];
  researching: ProjectOut;
  jobs: JobProgressOut[];
  ideas: IdeaOut[];
  project: ProjectOut;
  versions: VersionOut[];
  briefs: BriefOut[];
  claims: ClaimOut[];
  valueAdd: ValueAddOut;
  replicate: ReplicateOut;
  generated: number;
  replicated: { youtube_video_id: string; kind: string }[];
}

function initial(): ContentState {
  const project: ProjectOut = {
    id: PROJECT,
    channel_id: CHANNEL,
    idea_id: "i-3",
    parent_project_id: null,
    format: "LONG",
    state: "SCRIPT_REVIEW",
    resume_to_state: null,
    working_title: "Why octopuses dream",
    packaging_promise: {
      title_idea: "Why octopuses dream",
      thumbnail_text_idea: "THEY DREAM?",
      promise_statement: "What scientists saw when sleeping octopuses changed colour, and what it may mean.",
    },
    target_duration_s: 480,
    render_profile: { profile: "LONG_1080" },
    locked_script_version_id: null,
    originality_score: null,
    is_test: false,
    version: 1,
    created_at: NOW,
    updated_at: NOW,
    allowed_commands: ["approve-script", "request-script-changes", "pause", "cancel"],
    checks: [
      { code: "no_contradicted_claims", ok: true, message: null },
      { code: "owner_value_add", ok: false, message: "Add your own value: 0 of 1 owner fields filled." },
      { code: "duration_fits_format", ok: true, message: null },
    ],
  };
  const researchJob: JobProgressOut = {
    id: "jp-1",
    kind: "content.research",
    label: "Research",
    entity_type: "video_project",
    entity_id: "p-102",
    project_id: "p-102",
    status: "RUNNING",
    pct: 35,
    stage: "Reading articles (4 of 9)",
    message: null,
    hint: null,
    eta_s: 75,
    queued_at: NOW,
    started_at: NOW,
    updated_at: NOW,
    finished_at: null,
    link: "/projects/p-102/script",
  };
  const researching: ProjectOut = {
    ...project,
    id: "p-102",
    idea_id: null,
    state: "RESEARCHING",
    working_title: "Run a code assistant on your own PC",
    packaging_promise: null,
    allowed_commands: ["retry-research", "pause", "cancel"],
    checks: [],
    progress: researchJob,
  };
  const jobs: JobProgressOut[] = [
    {
      ...researchJob,
      id: "jp-2",
      kind: "content.ideas",
      label: "New ideas",
      entity_type: "channel",
      entity_id: CHANNEL,
      project_id: null,
      status: "QUEUED",
      pct: 0,
      stage: "Waiting for a free worker",
      eta_s: null,
      started_at: null,
      link: `/channels/${CHANNEL}/ideas`,
    },
  ];
  const version: VersionOut = {
    id: "sv-1",
    version: 1,
    author_type: "AGENT",
    author_id: "A11_SCRIPTWRITING",
    word_count: 1175,
    est_duration_s: 470,
    content_sha256: "a".repeat(64),
    locked: false,
    fact_check: "DONE",
    created_at: NOW,
    body: longScript,
    plain_text: "I gave five free AI note apps the same messy lecture notes for a week…",
    findings: [],
    hook_s: 12.4,
  };
  return {
    ideas: [
      idea({}),
      idea({
        id: "i-2",
        title: "How I budget as a student in 2026",
        state: "SHORTLISTED",
        source: "OWNER",
        duplicate: true,
        similarity_max: "0.91",
        similar_to_id: "i-9",
        similar_to_title: "My student budget for 2026, explained",
      }),
      idea({
        id: "i-3",
        title: "Why octopuses dream",
        state: "IN_PRODUCTION",
        calendar_date: "2026-11-20",
        project_id: PROJECT,
        format: "LONG",
      }),
    ],
    art: {
      channel_id: CHANNEL,
      channel_name: "Calm Science",
      blueprint: {
        strategy_id: "st-1",
        status: "APPROVED",
        palette: ["#0F172A", "#F8FAFC", "#22C55E", "#38BDF8"],
        default_tagline: "Calm science, explained in plain words",
      },
      logos: [],
      banners: [],
      chosen_logo: null,
      chosen_banner: null,
      watermark: null,
      job: null,
    },
    artRequests: [],
    watermarkUploads: [],
    project,
    researching,
    jobs,
    versions: [version],
    briefs: [
      {
        id: "b-1",
        version: 1,
        status: "APPROVED",
        created_at: NOW,
        content: {
          summary:
            "Researchers filmed sleeping octopuses changing colour in patterns similar to awake hunting.",
          open_questions: ["No source says whether this is dreaming in the human sense."],
          claims: [
            { id: "c1", text: "Sleeping octopuses show active colour changes.", verdict: "SUPPORTED" },
          ],
        },
      },
    ],
    claims: [
      {
        id: "cl-1",
        subject_type: "RESEARCH_BRIEF",
        subject_id: "b-1",
        claim_text: "c1: Sleeping octopuses show active colour changes.",
        verdict: "SUPPORTED",
        explanation: "The source describes it.",
        sources: [
          { id: "d-1", url: "https://en.wikipedia.org/wiki/Octopus", title: "Octopus — Wikipedia (en)" },
        ],
        owner_override_reason: null,
        overridden_at: null,
      },
      {
        id: "cl-2",
        subject_type: "SCRIPT_VERSION",
        subject_id: "sv-1",
        claim_text: "All octopuses dream every night.",
        verdict: "CONTRADICTED",
        explanation: "The source only reports one species in a lab.",
        sources: [
          { id: "d-1", url: "https://en.wikipedia.org/wiki/Octopus", title: "Octopus — Wikipedia (en)" },
        ],
        owner_override_reason: null,
        overridden_at: null,
      },
    ],
    valueAdd: {
      own_opinion: null,
      own_experience: null,
      own_data: null,
      own_examples: null,
      owner_voice: "NONE",
      owner_footage: false,
      owner_photos: false,
      score: "0.00",
      filled_fields: [],
      min_chars: 30,
      updated_at: null,
    },
    replicate: {
      winners: [
        {
          youtube_video_id: "abcDEF12345",
          title: "My 30-day student budget",
          project_id: "p-9",
          published_at: null,
          views: null,
          multiple: null,
        },
      ],
      variations: [
        idea({
          id: "i-4",
          title: "My student budget, one year later",
          source: "REPLICATE",
          variation_kind: "UPDATE",
          similarity_to_source: "0.48",
        }),
      ],
    },
    generated: 0,
    replicated: [],
  };
}

/** The list form of a script version (no body, text or findings). */
/** Mirror of tubeforge.content.scripts.open_owner_slots: [[OWNER: …]] places still empty. */
export function openOwnerSlots(body: Record<string, unknown>) {
  const b = body as {
    hook?: { text?: string };
    promise_delivery?: { text?: string };
    sections?: { text?: string }[];
    payoff?: string;
    cta?: string;
  };
  const fields: [string, string][] = [
    ["hook", b.hook?.text ?? ""],
    ["promise_delivery", b.promise_delivery?.text ?? ""],
    ...(b.sections ?? []).map((s, i): [string, string] => [`sections.${String(i)}`, s.text ?? ""]),
    ["payoff", b.payoff ?? ""],
    ["cta", b.cta ?? ""],
  ];
  return fields.flatMap(([field, text]) =>
    [...text.matchAll(/\[\[OWNER:[^\]]*\]\]/g)].map((m) => ({
      field,
      marker: m[0],
      prompt: m[0].slice("[[OWNER:".length, -2).trim(),
    })),
  );
}

export function versionSummary(v: VersionOut): VersionSummaryOut {
  return {
    id: v.id,
    version: v.version,
    author_type: v.author_type,
    author_id: v.author_id,
    word_count: v.word_count,
    est_duration_s: v.est_duration_s,
    content_sha256: v.content_sha256,
    locked: v.locked,
    fact_check: v.fact_check,
    created_at: v.created_at,
  };
}

export let content = initial();

export function resetContentApi(): void {
  content = initial();
}

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { title: code, status, code, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );

export const contentHandlers: HttpHandler[] = [
  http.get("/api/v1/channels/:id/ideas", ({ request }) => {
    const state = new URL(request.url).searchParams.get("state");
    return HttpResponse.json({
      items: content.ideas.filter((i) => !state || i.state === state),
      next_cursor: null,
    });
  }),
  http.post("/api/v1/channels/:id/ideas/generate", () => {
    content.generated += 1;
    return HttpResponse.json({ job_id: 21, status: "QUEUED" }, { status: 202 });
  }),
  http.post("/api/v1/channels/:id/ideas/replicate", async ({ request }) => {
    const body = (await request.json()) as { youtube_video_id: string; kind: string };
    if (!content.replicate.winners.some((w) => w.youtube_video_id === body.youtube_video_id))
      return problem(404, "NOT_FOUND", "That video is not one of this channel's own videos.");
    content.replicated.push(body);
    return HttpResponse.json({ job_id: 22, status: "QUEUED" }, { status: 202 });
  }),
  http.post("/api/v1/channels/:id/ideas", async ({ request }) => {
    const body = (await request.json()) as { title: string; angle: string; format: "LONG" | "SHORT" };
    if (/guarantee/i.test(body.title + body.angle))
      return problem(
        422,
        "FORBIDDEN_PHRASE",
        "“guaranteed” makes a promise TubeForge cannot keep. Please reword it.",
      );
    const created = idea({
      id: `i-${String(content.ideas.length + 10)}`,
      ...body,
      source: "OWNER",
      packaging_promise: null,
    });
    content.ideas = [created, ...content.ideas];
    return HttpResponse.json(created, { status: 201 });
  }),
  http.get("/api/v1/channels/:id/replicate", () => HttpResponse.json(content.replicate)),
  http.post("/api/v1/ideas/:id/commands/:cmd", async ({ params, request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      date?: string | null;
      override_reason?: string | null;
    };
    const found = content.ideas.find((i) => i.id === params.id);
    if (!found) return problem(404, "NOT_FOUND", "No such idea.");
    if (
      params.cmd === "approve" &&
      found.duplicate &&
      !(body.override_reason && body.override_reason.length >= 20)
    )
      return problem(
        409,
        "GUARD_FAILED",
        "Too similar to an existing idea (0.91 ≥ 0.85); give a reason to override.",
      );
    const next: Record<string, IdeaOut["state"]> = {
      shortlist: "SHORTLISTED",
      schedule: "SCHEDULED",
      approve: "IN_PRODUCTION",
      discard: "DISCARDED",
    };
    const updated: IdeaOut = {
      ...found,
      state: next[String(params.cmd)] ?? found.state,
      calendar_date: params.cmd === "schedule" ? (body.date ?? null) : found.calendar_date,
      project_id: params.cmd === "approve" ? PROJECT : found.project_id,
    };
    content.ideas = content.ideas.map((i) => (i.id === found.id ? updated : i));
    const project_id = params.cmd === "approve" ? PROJECT : null;
    return HttpResponse.json(
      { idea: updated, transition_id: 1, project_id, job_ids: project_id ? [23] : [] },
      { status: project_id ? 202 : 200 },
    );
  }),
  http.get("/api/v1/calendar", () =>
    HttpResponse.json({
      items: content.ideas
        .filter((i) => i.calendar_date)
        .map((i) => ({
          id: i.id,
          date: i.calendar_date,
          channel_id: i.channel_id,
          title: i.title,
          format: i.format,
          state: i.state,
          project_id: i.project_id,
          project_state: i.project_id ? content.project.state : null,
        })),
    }),
  ),
  http.patch("/api/v1/calendar/items/:id", async ({ params, request }) => {
    const { date } = (await request.json()) as { date: string };
    content.ideas = content.ideas.map((i) => (i.id === params.id ? { ...i, calendar_date: date } : i));
    const it = content.ideas.find((i) => i.id === params.id);
    return HttpResponse.json({ ...it, date, project_state: null });
  }),
  http.get("/api/v1/projects", () =>
    HttpResponse.json({ items: [content.project, content.researching], next_cursor: null }),
  ),
  http.get("/api/v1/projects/:id", ({ params }) =>
    HttpResponse.json(params.id === content.researching.id ? content.researching : content.project),
  ),
  http.get("/api/v1/channels/:id/channel-art", () => HttpResponse.json(content.art)),
  http.post("/api/v1/channels/:id/channel-art/generate", async ({ request }) => {
    const body = (await request.json()) as { tagline?: string | null };
    content.artRequests.push(body);
    const batch = (content.art.logos[0]?.batch ?? 0) + 1;
    content.art = withPicks({
      ...content.art,
      logos: [1, 2, 3].map((v) => art("LOGO", v, batch)),
      banners: [1, 2, 3].map((v) => art("BANNER", v, batch)),
    });
    return HttpResponse.json({ job_id: 7 }, { status: 202 });
  }),
  http.post("/api/v1/channels/:id/channel-art/:artId/choose", ({ params }) => {
    const pick = [...content.art.logos, ...content.art.banners].find((a) => a.id === params.artId);
    if (!pick) return problem(404, "NOT_FOUND", "No such logo or banner for this channel.");
    const mark = (list: ArtOut[]) =>
      list.map((a) => (a.role === pick.role ? { ...a, chosen: a.id === pick.id } : a));
    content.art = withPicks({
      ...content.art,
      logos: mark(content.art.logos),
      banners: mark(content.art.banners),
    });
    return HttpResponse.json(content.art);
  }),
  http.post("/api/v1/channels/:id/watermark", ({ request }) => {
    const confirmed = new URL(request.url).searchParams.get("confirm_owned") === "true";
    if (!confirmed)
      return problem(422, "CONFIRM_OWNERSHIP", "Only your own brand logo can become the watermark.");
    content.watermarkUploads.push({ type: request.headers.get("Content-Type") ?? "", confirmed });
    content.art = { ...content.art, watermark: art("WATERMARK", 1, 1) };
    return HttpResponse.json({ job_id: 8 }, { status: 202 });
  }),
  http.get("/api/v1/assets", () => {
    const items: AssetOut[] = [...content.art.logos, ...content.art.banners].map((a) => ({
      id: a.asset_id,
      channel_id: CHANNEL,
      project_id: null,
      kind: "IMAGE",
      origin: "PROCEDURAL",
      mime_type: "image/png",
      size_bytes: a.size_bytes,
      width: a.width,
      height: a.height,
      created_at: NOW,
      rights_basis: "SYSTEM_GENERATED",
      licence: a.licence,
      commercial_use_allowed: true,
      download_url: a.download_url,
    }));
    return HttpResponse.json({ items, next_cursor: null });
  }),
  http.get("/api/v1/pipeline", ({ request }) =>
    HttpResponse.json(pipelineOut(new URL(request.url).searchParams.get("channel_id"))),
  ),
  http.post("/api/v1/projects/:id/commands/:cmd", ({ params }) => {
    if (params.cmd === "approve-script" && content.project.checks?.some((c) => !c.ok))
      return problem(409, "GUARD_FAILED", "Add your own value: 0 of 1 owner fields filled.");
    if (params.cmd === "approve-script") {
      content.project = {
        ...content.project,
        state: "STORYBOARDING",
        allowed_commands: ["pause", "cancel"],
        checks: [],
      };
      content.versions = content.versions.map((v, i) => (i === 0 ? { ...v, locked: true } : v));
    }
    return HttpResponse.json({ project: content.project, transition_id: 2, job_ids: [] });
  }),
  http.get("/api/v1/projects/:id/research", () => HttpResponse.json(content.briefs)),
  http.get("/api/v1/projects/:id/claims", () => HttpResponse.json(content.claims)),
  http.post("/api/v1/claims/:id/override", async ({ params, request }) => {
    const { reason } = (await request.json()) as { reason: string };
    content.claims = content.claims.map((c) =>
      c.id === params.id ? { ...c, owner_override_reason: reason, overridden_at: NOW } : c,
    );
    return HttpResponse.json(content.claims.find((c) => c.id === params.id));
  }),
  http.get("/api/v1/projects/:id/value-add", () => HttpResponse.json(content.valueAdd)),
  http.put("/api/v1/projects/:id/value-add", async ({ request }) => {
    const body = (await request.json()) as Partial<ValueAddOut>;
    const filled = (["own_experience", "own_opinion", "own_data", "own_examples"] as const).filter(
      (k) => (body[k] ?? "").length >= 30,
    );
    content.valueAdd = {
      ...content.valueAdd,
      ...body,
      filled_fields: filled,
      score: filled.length ? "25.00" : "0.00",
    };
    content.project = {
      ...content.project,
      checks: (content.project.checks ?? []).map((c) =>
        c.code === "owner_value_add"
          ? { ...c, ok: filled.length > 0, message: filled.length ? null : c.message }
          : c,
      ),
    };
    return HttpResponse.json(content.valueAdd);
  }),
  http.get("/api/v1/projects/:id/script/versions", () =>
    HttpResponse.json([...content.versions].sort((a, b) => b.version - a.version).map(versionSummary)),
  ),
  http.get("/api/v1/projects/:id/script/versions/:n", ({ params }) => {
    const v = content.versions.find((x) => x.version === Number(params.n));
    if (!v) return HttpResponse.json(v);
    const { _part_options: stored, ...body } = v.body as Record<string, unknown> & {
      _part_options?: Record<string, { kind: string; text: string }[]>;
    };
    const open = openOwnerSlots(body);
    const part_options = Object.fromEntries(
      Object.entries(stored ?? {}).filter(([m]) => open.some((o) => o.marker === m)),
    );
    return HttpResponse.json({ ...v, body, owner_slots: open, part_options });
  }),
  // Suggestions for one owner part: written at once here (the worker's A11 run in the real app).
  http.post("/api/v1/projects/:id/script/versions/:n/part-options", async ({ params, request }) => {
    const { marker } = (await request.json()) as { marker: string };
    const v = content.versions.find((x) => x.version === Number(params.n));
    if (!v || !openOwnerSlots(v.body).some((o) => o.marker === marker))
      return problem(409, "NOT_EDITABLE", "That part is not empty in this version.");
    const body = v.body as Record<string, unknown> & { _part_options?: Record<string, unknown> };
    v.body = {
      ...body,
      _part_options: {
        ...(body._part_options ?? {}),
        [marker]: [
          { kind: "FILL_IN", text: "I kept ___ because ___." },
          { kind: "QUESTION", text: "Which app would you keep?" },
          { kind: "NEUTRAL", text: "The app you keep is usually the one you open every day." },
        ],
      },
    };
    return HttpResponse.json({ job_id: 9, transition_id: null, status: "QUEUED" }, { status: 202 });
  }),
  http.post("/api/v1/projects/:id/script/versions", async ({ request }) => {
    const { body, based_on_version } = (await request.json()) as {
      body: Record<string, unknown>;
      based_on_version: number;
    };
    const latest = Math.max(...content.versions.map((v) => v.version));
    if (based_on_version !== latest)
      return problem(412, "VERSION_CONFLICT", `Version ${String(latest)} is the latest.`);
    const created: VersionOut = {
      ...(content.versions[0] as VersionOut),
      id: `sv-${String(latest + 1)}`,
      version: latest + 1,
      author_type: "OWNER",
      author_id: "owner",
      fact_check: "PENDING",
      body,
    };
    content.versions = [...content.versions, created];
    return HttpResponse.json({ ...created, owner_slots: openOwnerSlots(body) }, { status: 201 });
  }),
  http.get("/api/v1/projects/:id/script/diff", ({ request }) => {
    const q = new URL(request.url).searchParams;
    return HttpResponse.json({
      a: Number(q.get("a")),
      b: Number(q.get("b")),
      lines: ["--- v1", "+++ v2", "+A new line"],
    });
  }),
  http.post("/api/v1/projects/:id/script/regenerate", () =>
    HttpResponse.json({ job_id: 24, transition_id: 3, status: "QUEUED" }, { status: 202 }),
  ),
];
