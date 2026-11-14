/**
 * Unit tests (Vitest + msw/node) and the public demo build (`build:demo`, mocks/demo.ts): imitates the
 * real endpoints so components can run without a server. The normal build talks to the real backend.
 * Contract tests (Python + Playwright e2e) cover the real implementation.
 */
import { http, HttpResponse, type HttpHandler } from "msw";
import type {
  AgentOut,
  AgentRunOut,
  ChannelOut,
  ProviderOut,
  Controls,
  Me,
  NotificationOut,
  OAuthClientOut,
  Problem,
  SettingsOut,
  StepOut,
  UploadJobOut,
} from "../lib/api/client";

const OWNER: Me = {
  user: {
    id: "u-1",
    email: "owner@example.com",
    display_name: "Owner",
    timezone: "Asia/Karachi",
    mfa_enabled: false,
  },
  roles: ["OWNER"],
  permissions: [
    "dashboard.view",
    "emergency.activate",
    "emergency.clear",
    "security.view",
    "settings.manage",
  ],
  mfa_enabled: false,
  mfa_passed: true,
  reauth_valid_until: null,
};

interface State {
  agents: AgentOut[];
  runs: AgentRunOut[];
  providers: ProviderOut[];
  channels: ChannelOut[];
  steps: StepOut[];
  clients: OAuthClientOut[];
  notifications: NotificationOut[];
  upload: UploadJobOut | null;
  uploadPolls: number;
  signedIn: boolean;
  controls: Controls;
  reauthUntil: number;
  settings: SettingsOut;
}

export function testSettings(): SettingsOut {
  return initial().settings;
}

const STEP_CODES: StepOut["step_code"][] = [
  "CREATE_GOOGLE_ACCOUNT",
  "CREATE_CHANNEL",
  "VERIFY_PHONE",
  "CREATE_GCP_PROJECT",
  "ENABLE_APIS",
  "CONSENT_SCREEN",
  "OAUTH_CLIENT",
  "PRIVACY_POLICY",
  "CONNECT",
  "TEST_UPLOAD",
];

export function testChannel(overrides: Partial<ChannelOut> = {}): ChannelOut {
  return {
    id: "ch-1",
    name: "Calm Science",
    state: "CONNECTED",
    youtube_channel_id: "UC" + "a".repeat(22),
    youtube_handle: "@calmscience",
    content_language: "en",
    audience_timezone: "UTC",
    operating_mode: "MANUAL",
    private_only_mode: true,
    is_test_channel: true,
    is_monetised: false,
    local_only: false,
    successful_private_test_uploads: 0,
    privacy_policy_url: null,
    oauth_status: "ACTIVE",
    oauth_expiring_soon: false,
    version: 1,
    created_at: "2026-11-08T00:00:00Z",
    updated_at: "2026-11-08T00:00:00Z",
    ...overrides,
  };
}

export function testAgent(overrides: Partial<AgentOut> = {}): AgentOut {
  return {
    agent_code: "T00_HELLO",
    name: "Hello test agent",
    kind: "TEST",
    is_auditor: false,
    enabled: true,
    paused: false,
    runnable: true,
    version: "1.0.0",
    prompt_version: "v1.0",
    provider_chain: ["gemini:gemini-3.5-flash-lite", "ollama:qwen2.5:1.5b"],
    limits: { calls_per_day: 20, tokens_per_day: 20000, max_runtime_s: 60 },
    updated_at: "2026-11-09T00:00:00Z",
    etag: "e1",
    stats_24h: { runs: 0, success_pct: null, p50_ms: null, tokens: 0 },
    ...overrides,
  };
}

export function testProvider(overrides: Partial<ProviderOut> = {}): ProviderOut {
  return {
    code: "gemini:gemini-3.5-flash-lite",
    family: "gemini",
    capability: "LLM",
    tier: "F",
    enabled: true,
    paid_activation_step: 0,
    licence: "Gemini API terms",
    licence_url: null,
    commercial_use: "YES",
    data_use_training: true,
    published_limits: { placeholder: true },
    limits: [{ metric: "REQUESTS", period: "DAY", limit_value: 200 }],
    has_key: false,
    needs_key: true,
    verified_at: "2026-11-09",
    verified_url: "https://ai.google.dev/gemini-api/docs/pricing",
    reverify_due: false,
    notes: null,
    ...overrides,
  };
}

function initial(): State {
  return {
    agents: [
      testAgent(),
      testAgent({
        agent_code: "A32_COST_MONITOR",
        name: "Cost monitor",
        kind: "DETERMINISTIC",
        is_auditor: true,
        runnable: false,
        provider_chain: [],
        etag: "e2",
      }),
    ],
    runs: [],
    providers: [
      testProvider(),
      testProvider({
        code: "ollama:qwen2.5:1.5b",
        family: "ollama",
        tier: "L",
        has_key: true,
        needs_key: false,
        data_use_training: false,
        limits: [],
      }),
      testProvider({
        code: "gemini:gemini-3.1-pro-preview",
        tier: "P",
        enabled: false,
        notes: "Paid.",
        limits: [],
      }),
    ],
    channels: [testChannel()],
    steps: STEP_CODES.map((code) => ({
      step_code: code,
      status: code === "CONNECT" ? "DONE" : "TODO",
      completed_at: null,
      notes: null,
      system: code === "CONNECT" || code === "TEST_UPLOAD",
    })),
    clients: [],
    notifications: [
      {
        id: "n-1",
        channel_id: "ch-1",
        event_type: "oauth.expiring",
        severity: "CRITICAL",
        title: "YouTube needs you to sign in again",
        body: "Calm Science: access to YouTube stopped working.",
        link: "/channels/ch-1/onboarding",
        created_at: "2026-11-08T09:00:00Z",
        read_at: null,
      },
    ],
    upload: null,
    uploadPolls: 0,
    signedIn: true,
    controls: {
      emergency_stop: { active: false, reason: null, since: null, by: null },
      publishing_kill_switch: false,
      kill_switches: [],
    },
    reauthUntil: 0,
    settings: {
      night_render_start: "01:00",
      night_render_end: "07:00",
      quiet_hours_start: "23:00",
      quiet_hours_end: "08:00",
      owner_timezone: "Asia/Karachi",
      disk_budget_gb: 200,
      settings: {},
      version: 1,
      updated_at: "2026-11-08T00:00:00Z",
    },
  };
}

let state = initial();

export function resetTestApi(overrides: Partial<State> = {}): void {
  state = { ...initial(), ...overrides };
}

function problem(status: number, code: string, title: string, detail: string) {
  const body: Problem = { title, status, code, detail, request_id: "req-test" };
  return HttpResponse.json(body, { status, headers: { "Content-Type": "application/problem+json" } });
}

const unauth = () => problem(401, "UNAUTHENTICATED", "Not signed in", "Please sign in.");

export const testApiHandlers: HttpHandler[] = [
  http.get("/api/v1/auth/me", () => (state.signedIn ? HttpResponse.json(OWNER) : unauth())),
  http.post("/api/v1/auth/login", async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.password !== "right password") {
      return problem(401, "BAD_CREDENTIALS", "Sign-in failed", "The e-mail or password is not correct.");
    }
    state.signedIn = true;
    return HttpResponse.json({ user: OWNER.user, mfa_required: false });
  }),
  http.post("/api/v1/auth/logout", () => {
    state.signedIn = false;
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("/api/v1/auth/reauth", async ({ request }) => {
    const body = (await request.json()) as { password: string };
    if (body.password === "wrong" || !body.password) {
      return problem(401, "BAD_CREDENTIALS", "Not accepted", "That password (or code) was not accepted.");
    }
    state.reauthUntil = Date.now() + 5 * 60_000;
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("/api/v1/system/controls", () => (state.signedIn ? HttpResponse.json(state.controls) : unauth())),
  http.post("/api/v1/system/emergency-stop", async ({ request }) => {
    if (!request.headers.get("Idempotency-Key"))
      return problem(400, "IDEMPOTENCY_KEY_REQUIRED", "Missing", "key");
    const body = (await request.json()) as { reason?: string };
    state.controls = {
      ...state.controls,
      emergency_stop: {
        active: true,
        reason: body.reason || null,
        since: new Date().toISOString(),
        by: "u-1",
      },
    };
    return HttpResponse.json(state.controls);
  }),
  http.post("/api/v1/system/emergency-stop/clear", () => {
    if (Date.now() > state.reauthUntil) {
      return problem(403, "REAUTH_REQUIRED", "Confirm it's you", "This action needs your password again.");
    }
    state.controls = {
      ...state.controls,
      emergency_stop: { active: false, reason: null, since: null, by: null },
    };
    return HttpResponse.json(state.controls);
  }),
  http.get("/api/v1/settings", () =>
    HttpResponse.json(state.settings, { headers: { ETag: `"${state.settings.version}"` } }),
  ),
  http.put("/api/v1/settings", async ({ request }) => {
    const ifMatch = request.headers.get("If-Match");
    if (ifMatch !== `"${state.settings.version}"`) {
      return problem(412, "VERSION_CONFLICT", "Changed elsewhere", "Reload and try again.");
    }
    const body = (await request.json()) as Partial<SettingsOut>;
    state.settings = { ...state.settings, ...body, version: state.settings.version + 1 };
    return HttpResponse.json(state.settings);
  }),
  http.get("/api/v1/auth/sessions", () => HttpResponse.json([])),
  http.get("/api/v1/audit-log", () =>
    HttpResponse.json({
      items: [
        {
          id: 2,
          occurred_at: "2026-11-08T09:12:00Z",
          actor_type: "OWNER",
          actor_id: "u-1",
          action: "auth.login",
          entity_type: "user",
          entity_id: "u-1",
          channel_id: null,
          details: {},
          request_id: null,
          row_hash: "b".repeat(64),
        },
      ],
      next_cursor: null,
    }),
  ),
  http.get("/api/v1/audit-log/verify-chain", () =>
    HttpResponse.json({ ok: true, checked: 2, first_broken_id: null }),
  ),
  http.get("/api/v1/security-events", () => HttpResponse.json({ items: [], next_cursor: null })),
  http.get("/api/v1/agents", () => HttpResponse.json(state.agents)),
  http.patch("/api/v1/agents/:code", async ({ params, request }) => {
    const agent = state.agents.find((a) => a.agent_code === params.code);
    if (!agent) return problem(404, "NOT_FOUND", "Not found", "No such agent.");
    if (request.headers.get("If-Match") !== `"${agent.etag}"`)
      return problem(412, "VERSION_CONFLICT", "Changed elsewhere", "Reload.");
    const body = (await request.json()) as Partial<AgentOut>;
    Object.assign(agent, { ...body, limits: { ...agent.limits, ...body.limits }, etag: agent.etag + "x" });
    return HttpResponse.json(agent);
  }),
  http.post("/api/v1/agents/:code/run", async ({ params, request }) => {
    const body = (await request.json()) as { input: { name: string } };
    state.runs = [
      {
        id: `r-${String(state.runs.length + 1)}`,
        agent_code: String(params.code),
        channel_id: null,
        project_id: null,
        status: "SUCCEEDED",
        provider_code: "gemini:gemini-3.5-flash-lite",
        model: "gemini-3.5-flash-lite",
        tokens_in: 30,
        tokens_out: 10,
        duration_ms: 420,
        repair_attempted: false,
        error_class: null,
        error_detail: null,
        input: body.input,
        output: { greeting: `Hello ${body.input.name}`, language: "en" },
        started_at: "2026-11-09T10:00:00Z",
        finished_at: "2026-11-09T10:00:01Z",
      },
      ...state.runs,
    ];
    return HttpResponse.json({ job_id: 1, agent_code: params.code }, { status: 202 });
  }),
  http.get("/api/v1/agent-runs", () => HttpResponse.json({ items: state.runs, next_cursor: null })),
  http.post("/api/v1/system/kill-switches", async ({ request }) => {
    const body = (await request.json()) as { target_id: string };
    const agent = state.agents.find((a) => a.agent_code === body.target_id);
    if (agent) agent.paused = true;
    return HttpResponse.json(state.controls);
  }),
  http.get("/api/v1/providers", () => HttpResponse.json(state.providers)),
  http.put("/api/v1/providers/:code/credentials", ({ params }) => {
    const family = String(params.code).split(":")[0];
    for (const p of state.providers) if (p.family === family) p.has_key = true;
    return new HttpResponse(null, { status: 204 });
  }),
  http.patch("/api/v1/providers/:code", async ({ params, request }) => {
    const p = state.providers.find((x) => x.code === params.code);
    if (!p) return problem(404, "NOT_FOUND", "Not found", "No such provider.");
    const body = (await request.json()) as Partial<ProviderOut>;
    Object.assign(p, body);
    return HttpResponse.json({ provider: p, warnings: [] });
  }),
  http.post("/api/v1/providers/:code/paid-activation/step1", ({ params }) =>
    HttpResponse.json({
      code: params.code,
      estimate: {},
      confirm_phrase: `ENABLE PAID ${String(params.code)}`,
      earliest_step2_at: new Date(Date.now() + 60_000).toISOString(),
    }),
  ),
  http.get("/api/v1/usage", () =>
    HttpResponse.json([
      {
        provider_code: "gemini:gemini-3.5-flash-lite",
        metric: "REQUESTS",
        period: "DAY",
        period_key: "2026-11-09",
        used: 50,
        limit: 200,
        pct: 25,
        resets_at: "2026-11-10T08:00:00Z",
      },
    ]),
  ),
  http.get("/api/v1/costs/summary", () =>
    HttpResponse.json({ month: "2026-11", spent_minor: 0, paid_enabled: [] }),
  ),
  http.get("/api/v1/budgets", () => HttpResponse.json([])),
  http.get("/api/v1/channels", () => HttpResponse.json({ items: state.channels, next_cursor: null })),
  http.post("/api/v1/channels", async ({ request }) => {
    const body = (await request.json()) as { name: string; content_language: string };
    const ch = testChannel({
      id: `ch-${String(state.channels.length + 1)}`,
      name: body.name,
      content_language: body.content_language,
      state: "APPROVED",
      oauth_status: "NOT_CONNECTED",
      youtube_handle: null,
    });
    state.channels = [...state.channels, ch];
    return HttpResponse.json(ch, { status: 201 });
  }),
  http.get("/api/v1/channels/:id", ({ params }) => {
    const ch = state.channels.find((c) => c.id === params.id);
    return ch ? HttpResponse.json(ch) : problem(404, "NOT_FOUND", "Not found", "No such channel.");
  }),
  http.post("/api/v1/channels/:id/commands/:cmd", ({ params }) => {
    const ch = state.channels.find((c) => c.id === params.id);
    if (!ch) return problem(404, "NOT_FOUND", "Not found", "No such channel.");
    ch.state = params.cmd === "pause" ? "PAUSED" : params.cmd === "resume" ? "CONNECTED" : "ONBOARDING";
    return HttpResponse.json(ch);
  }),
  http.get("/api/v1/channels/:id/onboarding", () => HttpResponse.json(state.steps)),
  http.patch("/api/v1/channels/:id/onboarding/:code", async ({ params, request }) => {
    const body = (await request.json()) as { status: StepOut["status"] };
    const step = state.steps.find((s) => s.step_code === params.code);
    if (!step) return problem(404, "NOT_FOUND", "Not found", "No such step.");
    step.status = body.status;
    return HttpResponse.json(step);
  }),
  http.get("/api/v1/channels/:id/oauth/health", () =>
    HttpResponse.json({
      status: "ACTIVE",
      scopes: ["youtube.readonly", "youtube.upload"],
      expires_hint: "2026-11-15T00:00:00Z",
      expiring_soon: false,
      last_refresh_at: null,
      last_error: null,
      publishing_status: "TESTING",
    }),
  ),
  http.get("/api/v1/channels/:id/oauth/identity", () =>
    HttpResponse.json({
      youtube_channel_id: "UC" + "a".repeat(22),
      title: "Calm Science",
      handle: "@calmscience",
    }),
  ),
  http.get("/api/v1/oauth/clients", () => HttpResponse.json(state.clients)),
  http.post("/api/v1/oauth/clients", async ({ request }) => {
    const body = (await request.json()) as { label: string; client_id: string };
    const row: OAuthClientOut = {
      id: "oc-1",
      label: body.label,
      client_id: body.client_id,
      has_secret: true,
      gcp_project_id: null,
      publishing_status: "TESTING",
      created_at: "2026-11-08T00:00:00Z",
    };
    state.clients = [row];
    const step = state.steps.find((s) => s.step_code === "OAUTH_CLIENT");
    if (step) step.status = "DONE";
    return HttpResponse.json(row, { status: 201 });
  }),
  http.post("/api/v1/channels/:id/test-upload", ({ params }) => {
    state.uploadPolls = 0;
    state.upload = {
      id: "up-1",
      channel_id: String(params.id),
      project_id: "p-1",
      state: "PREFLIGHT",
      privacy_status: "private",
      made_for_kids: false,
      contains_synthetic_media: false,
      is_test: true,
      bytes_total: 11861,
      bytes_confirmed: 0,
      youtube_video_id: null,
      error_class: null,
      error_detail: null,
      created_at: "2026-11-08T00:00:00Z",
      updated_at: "2026-11-08T00:00:00Z",
    };
    return HttpResponse.json(state.upload, { status: 202 });
  }),
  http.get("/api/v1/uploads/:id", () => {
    if (!state.upload) return problem(404, "NOT_FOUND", "Not found", "No such upload.");
    state.uploadPolls += 1; // the second poll finds it finished
    if (state.uploadPolls >= 2)
      state.upload = {
        ...state.upload,
        state: "COMPLETED",
        bytes_confirmed: 11861,
        youtube_video_id: "vid-1",
      };
    return HttpResponse.json(state.upload);
  }),
  http.get("/api/v1/notifications/summary", () => {
    const unread = state.notifications.filter((n) => !n.read_at);
    return HttpResponse.json({
      unread: unread.length,
      critical_unread: unread.filter((n) => n.severity === "CRITICAL").length,
    });
  }),
  http.get("/api/v1/notifications", () =>
    HttpResponse.json({ items: state.notifications, next_cursor: null }),
  ),
  http.post("/api/v1/notifications/read-all", () => {
    state.notifications = state.notifications.map((n) => ({ ...n, read_at: "2026-11-08T10:00:00Z" }));
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("/api/v1/quota", () =>
    HttpResponse.json([
      {
        gcp_project: "default",
        buckets: [
          {
            bucket: "DEFAULT",
            daily_limit: 10000,
            usable: 9000,
            used: 900,
            held: 0,
            available: 8100,
            resets_at: "2026-11-09T08:00:00Z",
            resets_at_pkt: "13:00 PKT",
          },
        ],
        forecast: [],
      },
    ]),
  ),
];
