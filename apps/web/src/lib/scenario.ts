/** Dev scenario switcher: forces every page's data into one of the four standard states. */
export const SCENARIOS = ["success", "empty", "loading", "error"] as const;
export type Scenario = (typeof SCENARIOS)[number];

const KEY = "tf-scenario";
const listeners = new Set<() => void>();

function isScenario(v: unknown): v is Scenario {
  return typeof v === "string" && (SCENARIOS as readonly string[]).includes(v);
}

function initial(): Scenario {
  if (typeof window === "undefined") return "success";
  const fromUrl = new URLSearchParams(window.location.search).get("scenario");
  if (isScenario(fromUrl)) return fromUrl;
  try {
    const stored = window.localStorage.getItem(KEY);
    if (isScenario(stored)) return stored;
  } catch {
    // storage unavailable (private window): fall back to the default
  }
  return "success";
}

let current: Scenario = initial();

export function getScenario(): Scenario {
  return current;
}

export function setScenario(next: Scenario): void {
  current = next;
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    // ignore
  }
  listeners.forEach((l) => l());
}

export function subscribeScenario(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
