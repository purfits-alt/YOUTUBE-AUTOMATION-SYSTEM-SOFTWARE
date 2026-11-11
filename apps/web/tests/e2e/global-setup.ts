import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { request, type APIRequestContext, type FullConfig } from "@playwright/test";

/** Sign in once as the owner (created by the CI job / developer) and save the session cookies. */
export const STORAGE_STATE = "test-results/.auth/owner.json";

export const OWNER_EMAIL = process.env.TUBEFORGE_E2E_EMAIL ?? "owner@example.com";
export const OWNER_PASSWORD = process.env.TUBEFORGE_E2E_PASSWORD ?? "correct horse battery staple 42";

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://127.0.0.1:8765";
  const ctx = await request.newContext({ baseURL });
  const res = await ctx.post("/api/v1/auth/login", {
    data: { email: OWNER_EMAIL, password: OWNER_PASSWORD },
  });
  if (!res.ok()) {
    throw new Error(
      `e2e sign-in failed (${String(res.status())}): create the owner first, e.g. ` +
        "TUBEFORGE_OWNER_PASSWORD=... uv run tubeforge-admin create-owner --email owner@example.com",
    );
  }
  await seed(ctx);
  await ctx.storageState({ path: STORAGE_STATE });
  await ctx.dispose();
}

/** Where the seeded IDs are written for the specs (see helpers.ts). */
export const SEED_FILE = "test-results/.auth/seed.json";
export const SEED_CHANNEL = "Calm Science";

/**
 * Real data for the real pages (idempotent, so local re-runs reuse it): one test channel in setup,
 * and one real notification — produced by asking for a test upload before the channel is connected,
 * which the safety checks refuse (REFUSED_CHANNEL_STATE → audit + security event + notification).
 */
async function seed(ctx: APIRequestContext): Promise<void> {
  const state = await ctx.storageState();
  const csrf = state.cookies.find((c) => c.name === "tf_csrf")?.value ?? "";
  const headers = () => ({
    "X-CSRF-Token": decodeURIComponent(csrf),
    "Idempotency-Key": crypto.randomUUID(),
  });
  const list = (await (await ctx.get("/api/v1/channels?limit=100")).json()) as {
    items: { id: string; name: string }[];
  };
  let channel = list.items.find((c) => c.name === SEED_CHANNEL);
  if (!channel) {
    const created = await ctx.post("/api/v1/channels", {
      headers: headers(),
      data: { name: SEED_CHANNEL, content_language: "en", is_test_channel: true, is_monetised: false },
    });
    channel = (await created.json()) as { id: string; name: string };
    await ctx.post(`/api/v1/channels/${channel.id}/commands/start-onboarding`, { headers: headers() });
  }
  const summary = (await (await ctx.get("/api/v1/notifications/summary")).json()) as { unread: number };
  if (summary.unread === 0) {
    const refused = await ctx.post(`/api/v1/channels/${channel.id}/test-upload`, { headers: headers() });
    if (refused.status() !== 409)
      throw new Error(`seed: expected a refused test upload, got ${String(refused.status())}`);
  }
  // One real discovery report (queued: no worker runs in e2e) so Channel Discovery has data.
  const reports = (await (await ctx.get("/api/v1/niches/reports")).json()) as unknown[];
  if (reports.length === 0) {
    const started = await ctx.post("/api/v1/niches/reports", {
      headers: headers(),
      data: { avoid: ["crypto"] },
    });
    if (started.status() !== 202) throw new Error(`seed: discovery report, got ${String(started.status())}`);
  }
  mkdirSync(dirname(SEED_FILE), { recursive: true });
  writeFileSync(SEED_FILE, JSON.stringify({ channelId: channel.id }));
}
