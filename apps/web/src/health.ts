export type Health = { status: string; version: string };

export type HealthState =
  { kind: "loading" } | { kind: "ok"; health: Health } | { kind: "error"; message: string };

/** Phase 1 only: plain fetch. From Phase 3 the generated OpenAPI client is used. */
export async function fetchHealth(fetchImpl: typeof fetch = fetch): Promise<Health> {
  const res = await fetchImpl("/healthz", { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Backend returned ${res.status}`);
  return (await res.json()) as Health;
}
