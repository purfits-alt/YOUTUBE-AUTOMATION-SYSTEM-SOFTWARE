/**
 * Unit tests only (Vitest + msw/node): imitates the real Phase 3 endpoints so components can be tested
 * without a server. The browser never loads this file; it talks to the real FastAPI backend.
 * Contract tests (Python + Playwright e2e) cover the real implementation.
 */
import { http, HttpResponse, type HttpHandler } from "msw";
import type {
  ChannelOut,
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

function initial(): State {
  return {
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
