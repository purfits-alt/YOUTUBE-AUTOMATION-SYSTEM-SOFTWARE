import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Problem = Schemas["Problem"];
export type PageData = Schemas["PageData"];
export type Overview = Schemas["Overview"];
export type Shell = Schemas["Shell"];
export type Controls = Schemas["Controls"];
export type Row = Schemas["Row"];

export const API_BASE = "/api/v1";

/** Typed client generated from packages/shared/openapi.stub.json (Phase 3: the FastAPI spec). */
export const api = createClient<paths>({
  // Absolute URL so the same client works in the browser and in Node-based tests (jsdom).
  baseUrl: (typeof window !== "undefined" ? window.location.origin : "") + API_BASE,
  // Look fetch up on every call (not once at import) so test interceptors are honoured.
  fetch: (request: Request) => globalThis.fetch(request),
});

/** A failed request, carrying the RFC 9457 problem body. */
export class ProblemError extends Error {
  readonly problem: Problem;
  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ProblemError";
    this.problem = problem;
  }
}

function toProblem(error: unknown, status: number): Problem {
  if (error && typeof error === "object" && "title" in error && "code" in error) return error as Problem;
  return {
    title: "Request failed",
    status,
    code: status === 0 ? "NETWORK" : "HTTP_" + String(status),
    detail: "The server did not return a readable error.",
  };
}

type Reauth = () => Promise<void>;
let reauthHandler: Reauth | null = null;

/** The shell registers the ReauthModal here; a 403 REAUTH_REQUIRED opens it and retries once. */
export function setReauthHandler(handler: Reauth | null): void {
  reauthHandler = handler;
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Unwrap an openapi-fetch call: return data or throw ProblemError; handle step-up once. */
export async function call<T>(run: () => Promise<FetchResult<T>>): Promise<T> {
  let result = await run();
  if (result.error !== undefined && result.response.status === 403 && reauthHandler) {
    const problem = toProblem(result.error, 403);
    if (problem.code === "REAUTH_REQUIRED") {
      await reauthHandler();
      result = await run();
    }
  }
  if (result.error !== undefined) throw new ProblemError(toProblem(result.error, result.response.status));
  return result.data as T;
}

/**
 * Page data for registry pages. The path comes from the page registry at runtime, so it is
 * typed as one representative PageData path; openapi-fetch fills `{id}` for any path that has it.
 */
export function getPageData(apiPath: string, id: string | undefined, fallbackId: string): Promise<PageData> {
  const path = apiPath as "/niches/candidates/{id}";
  return call(() => api.GET(path, { params: { path: { id: id ?? fallbackId } } }));
}
