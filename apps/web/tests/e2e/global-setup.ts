import { request, type FullConfig } from "@playwright/test";

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
  await ctx.storageState({ path: STORAGE_STATE });
  await ctx.dispose();
}
