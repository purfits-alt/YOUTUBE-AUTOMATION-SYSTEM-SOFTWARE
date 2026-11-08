/**
 * Unit tests only (Vitest + msw/node): imitates the real Phase 3 endpoints so components can be tested
 * without a server. The browser never loads this file; it talks to the real FastAPI backend.
 * Contract tests (Python + Playwright e2e) cover the real implementation.
 */
import { http, HttpResponse, type HttpHandler } from "msw";
import type { Controls, Me, Problem, SettingsOut } from "../lib/api/client";

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
  signedIn: boolean;
  controls: Controls;
  reauthUntil: number;
  settings: SettingsOut;
}

export function testSettings(): SettingsOut {
  return initial().settings;
}

function initial(): State {
  return {
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
];
