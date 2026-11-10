import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";
import type { components as stubComponents, paths as stubPaths } from "./stub-schema";

/** Real API types, generated from packages/shared/openapi.json (the committed FastAPI contract). */
export type Schemas = components["schemas"];
export type Controls = Schemas["ControlsOut"];
export type Me = Schemas["MeOut"];
export type SettingsOut = Schemas["SettingsOut"];
export type SettingsIn = Schemas["SettingsIn"];
export type AuditLogEntry = Schemas["AuditLogOut"];
export type SecurityEventEntry = Schemas["SecurityEventOut"];
export type SessionInfo = Schemas["SessionOut"];
export type ChannelOut = Schemas["ChannelOut"];
export type StepOut = Schemas["StepOut"];
export type UploadJobOut = Schemas["UploadJobOut"];
export type OAuthClientOut = Schemas["OAuthClientOut"];
export type HealthOut = Schemas["HealthOut"];
export type IdentityOut = Schemas["IdentityOut"];
export type NotificationOut = Schemas["NotificationOut"];
export type NotificationSummary = Schemas["SummaryOut"];
export type ProjectQuota = Schemas["ProjectQuotaOut"];
export type AgentOut = Schemas["AgentOut"];
export type AgentRunOut = Schemas["AgentRunOut"];
export type ProviderOut = Schemas["ProviderOut"];
export type UsageLine = Schemas["UsageLine"];
export type BudgetOut = Schemas["BudgetOut"];
export type CostSummary = Schemas["CostSummary"];

/** Still-mocked endpoints (MSW until their phase), from packages/shared/openapi.stub.json. */
export type StubSchemas = stubComponents["schemas"];
export type PageData = StubSchemas["PageData"];
export type Overview = StubSchemas["Overview"];
export type Shell = StubSchemas["Shell"];
export type Row = StubSchemas["Row"];

/** RFC 9457 problem body (BACKEND_SPECIFICATION §1). */
export interface Problem {
  type?: string;
  title: string;
  status: number;
  detail?: string | null;
  code: string;
  request_id?: string;
  errors?: { field: string; message: string }[];
  guards?: { code: string; message: string; fix_href?: string }[];
  current_version?: number;
}

export const API_BASE = "/api/v1";
const origin = typeof window !== "undefined" ? window.location.origin : "";

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${name}=`;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(prefix))
    ?.slice(prefix.length);
}

/** Double-submit CSRF (OAUTH_SECURITY §2): every non-GET request carries the tf_csrf cookie value. */
const csrf: Middleware = {
  onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const token = readCookie("tf_csrf");
      if (token) request.headers.set("X-CSRF-Token", decodeURIComponent(token));
    }
    return request;
  },
};

// Look fetch up on every call (not once at import) so test interceptors are honoured.
const lateFetch = (request: Request) => globalThis.fetch(request);

/** Real backend (paths include /api/v1). */
export const api = createClient<paths>({ baseUrl: origin, fetch: lateFetch, credentials: "same-origin" });
api.use(csrf);

/** Mocked endpoints (paths relative to /api/v1). */
export const stubApi = createClient<stubPaths>({ baseUrl: origin + API_BASE, fetch: lateFetch });

/** A failed request, carrying the problem body. */
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

/** A fresh Idempotency-Key for one user action (BACKEND_SPECIFICATION §1). Reused on its retry. */
export function idempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Page data for registry pages that are still mocked. The path comes from the page registry at
 * runtime, so it is typed as one representative PageData path; openapi-fetch fills `{id}`.
 */
export function getPageData(apiPath: string, id: string | undefined, fallbackId: string): Promise<PageData> {
  const path = apiPath as "/niches/candidates/{id}";
  return call(() => stubApi.GET(path, { params: { path: { id: id ?? fallbackId } } }));
}
