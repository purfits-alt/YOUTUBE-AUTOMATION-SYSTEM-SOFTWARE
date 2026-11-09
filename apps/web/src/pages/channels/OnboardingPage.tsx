import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { useParams } from "react-router";
import { z } from "zod";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import {
  api,
  call,
  idempotencyKey,
  type ChannelOut,
  type StepOut,
  type UploadJobOut,
} from "../../lib/api/client";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import { inputCls, problemText, StateBadge, TokenBadge } from "./common";

/** Official help pages per step (checked 2026-11-09; see PROJECT_PROGRESS Phase 4). */
const HELP: Record<StepOut["step_code"], string[]> = {
  CREATE_GOOGLE_ACCOUNT: ["https://support.google.com/accounts/answer/27441"],
  CREATE_CHANNEL: ["https://support.google.com/youtube/answer/1646861"],
  VERIFY_PHONE: ["https://support.google.com/youtube/answer/171664"],
  CREATE_GCP_PROJECT: ["https://developers.google.com/workspace/guides/create-project"],
  ENABLE_APIS: [
    "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
    "https://developers.google.com/youtube/v3/getting-started",
  ],
  CONSENT_SCREEN: ["https://support.google.com/cloud/answer/15549945"],
  OAUTH_CLIENT: ["https://developers.google.com/identity/protocols/oauth2/native-app"],
  PRIVACY_POLICY: ["https://policies.google.com/privacy"],
  CONNECT: ["https://myaccount.google.com/permissions"],
  TEST_UPLOAD: ["https://studio.youtube.com"],
};
const FINAL = new Set(["COMPLETED", "FAILED", "REJECTED", "PROCESSING_FAILED"]);
const CONNECTABLE = new Set(["ONBOARDING", "CONNECTED", "ACTIVE", "PAUSED", "NEEDS_REAUTH"]);

function useChannelData(id: string) {
  const channel = useQuery({
    queryKey: ["channel", id],
    queryFn: () =>
      call(() => api.GET("/api/v1/channels/{channel_id}", { params: { path: { channel_id: id } } })),
  });
  const steps = useQuery({
    queryKey: ["onboarding", id],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/onboarding", { params: { path: { channel_id: id } } }),
      ),
  });
  const health = useQuery({
    queryKey: ["oauth-health", id],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/oauth/health", { params: { path: { channel_id: id } } }),
      ),
  });
  const clients = useQuery({
    queryKey: ["oauth-clients"],
    queryFn: () => call(() => api.GET("/api/v1/oauth/clients")),
  });
  return { channel, steps, health, clients };
}

function useRefresh(id: string) {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(
      [["channel", id], ["onboarding", id], ["oauth-health", id], ["channels"], ["oauth-clients"]].map((k) =>
        qc.invalidateQueries({ queryKey: k }),
      ),
    );
  };
}

// --------------------------------------------------------------------------------- OAuth client
const clientSchema = z.object({
  label: z.string().trim().min(1, "Enter a label").max(80),
  client_id: z
    .string()
    .trim()
    .regex(
      /^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$/,
      "Paste the Client ID ending in .apps.googleusercontent.com",
    ),
  client_secret: z.string().trim().max(200),
  gcp_project_id: z
    .string()
    .trim()
    .regex(/^([a-z][a-z0-9-]{4,28}[a-z0-9])?$/, "Use the project ID (lower-case letters, digits, dashes)"),
});
type ClientForm = z.infer<typeof clientSchema>;

function OAuthClientPanel({ onSaved }: { onSaved: () => Promise<void> }) {
  const clients = useQuery({
    queryKey: ["oauth-clients"],
    queryFn: () => call(() => api.GET("/api/v1/oauth/clients")),
  });
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<ClientForm>({
    resolver: zodResolver(clientSchema),
    defaultValues: { label: "TubeForge desktop", client_id: "", client_secret: "", gcp_project_id: "" },
  });
  const existing = clients.data?.[0];
  if (existing)
    return (
      <p className="text-sm" data-testid="oauth-client-registered">
        {t("onboarding.clientRegistered", { label: existing.label })}{" "}
        <code className="break-all text-xs text-muted">{existing.client_id}</code>{" "}
        <Badge tone="info">{t(`onboarding.publishing.${existing.publishing_status}`)}</Badge>
      </p>
    );
  const save = handleSubmit(async (v) => {
    setError(null);
    try {
      await call(() =>
        api.POST("/api/v1/oauth/clients", {
          body: {
            label: v.label,
            client_id: v.client_id,
            publishing_status: "TESTING",
            ...(v.client_secret ? { client_secret: v.client_secret } : {}),
            ...(v.gcp_project_id ? { gcp_project_id: v.gcp_project_id } : {}),
          },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      await onSaved();
    } catch (e) {
      setError(problemText(e));
    }
  });
  const field = (name: keyof ClientForm, label: string, type = "text", hint?: string) => (
    <div>
      <label htmlFor={`oc-${name}`} className="block text-sm font-medium">
        {label}
      </label>
      <input id={`oc-${name}`} type={type} autoComplete="off" className={inputCls} {...register(name)} />
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {formState.errors[name] && (
        <p role="alert" className="mt-1 text-sm text-danger-text">
          {formState.errors[name]?.message}
        </p>
      )}
    </div>
  );
  return (
    <form
      onSubmit={(e) => void save(e)}
      noValidate
      className="grid gap-3 sm:grid-cols-2"
      data-testid="oauth-client-form"
    >
      {field("label", t("onboarding.clientLabel"))}
      {field("gcp_project_id", t("onboarding.clientProject"), "text", t("onboarding.clientProjectHint"))}
      {field("client_id", t("onboarding.clientId"))}
      {field("client_secret", t("onboarding.clientSecret"), "password", t("onboarding.clientSecretHint"))}
      {error && (
        <p
          role="alert"
          className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-text sm:col-span-2"
        >
          {error}
        </p>
      )}
      <div className="sm:col-span-2">
        <Button type="submit" variant="primary" disabled={formState.isSubmitting}>
          {t("onboarding.saveClient")}
        </Button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------------------- privacy policy
function PrivacyPanel({ channel, onSaved }: { channel: ChannelOut; onSaved: () => Promise<void> }) {
  const [url, setUrl] = useState(channel.privacy_policy_url ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setError(null);
    if (!/^https:\/\/\S{3,490}$/.test(url)) {
      setError(t("onboarding.privacyInvalid"));
      return;
    }
    try {
      await call(() =>
        api.PATCH("/api/v1/channels/{channel_id}", {
          params: { path: { channel_id: channel.id } },
          body: { privacy_policy_url: url },
          headers: { "If-Match": `"${String(channel.version)}"` },
        }),
      );
      await onSaved();
    } catch (e) {
      setError(problemText(e));
    }
  };
  return (
    <div className="space-y-2">
      <label htmlFor="privacy-url" className="block text-sm font-medium">
        {t("onboarding.privacyUrl")}
      </label>
      <div className="flex flex-wrap gap-2">
        <input
          id="privacy-url"
          type="url"
          inputMode="url"
          placeholder="https://<your-github-name>.github.io/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE/privacy.html"
          className={`${inputCls} mt-0 min-w-0 flex-1`}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Button variant="primary" onClick={() => void save()}>
          {t("actions.save")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger-text">
          {error}
        </p>
      )}
    </div>
  );
}

// -------------------------------------------------------------------------------------- connect
function ConnectPanel({ channel, onDone }: { channel: ChannelOut; onDone: () => Promise<void> }) {
  const toast = useToast();
  const health = useQuery({
    queryKey: ["oauth-health", channel.id],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/oauth/health", {
          params: { path: { channel_id: channel.id } },
        }),
      ),
  });
  const needsIdentity = channel.state === "ONBOARDING" && health.data?.status === "ACTIVE";
  const identity = useQuery({
    queryKey: ["oauth-identity", channel.id],
    enabled: needsIdentity,
    retry: false,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/oauth/identity", {
          params: { path: { channel_id: channel.id } },
        }),
      ),
  });
  const [busy, setBusy] = useState(false);
  const connect = async () => {
    setBusy(true);
    try {
      const r = await call(() =>
        api.POST("/api/v1/oauth/youtube/start", {
          body: { channel_id: channel.id, features: [] },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      window.location.assign(r.authorization_url); // Google's consent page; it returns to /oauth/callback
    } catch (e) {
      toast(problemText(e), "danger");
      setBusy(false);
    }
  };
  const confirm = async (ytId: string) => {
    setBusy(true);
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/oauth/confirm-identity", {
          params: { path: { channel_id: channel.id } },
          body: { youtube_channel_id: ytId },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      toast(t("onboarding.confirmed"));
      await onDone();
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  if (needsIdentity) {
    if (identity.isPending) return <p className="text-sm text-muted">{t("onboarding.readingIdentity")}</p>;
    if (identity.isError)
      return <ProblemDisplay problem={asProblem(identity.error)} onRetry={() => void identity.refetch()} />;
    const who = identity.data;
    return (
      <div className="space-y-3 rounded-lg bg-info-soft p-4 text-info-text" data-testid="identity-confirm">
        <p className="text-sm">{t("onboarding.identityQuestion")}</p>
        <p className="text-base font-semibold" dir="auto">
          {who.title ?? who.youtube_channel_id}{" "}
          {who.handle && <span className="font-normal">({who.handle})</span>}
        </p>
        <p className="text-xs break-all">{who.youtube_channel_id}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={busy} onClick={() => void confirm(who.youtube_channel_id)}>
            {t("onboarding.identityYes")}
          </Button>
          <Button disabled={busy} onClick={() => void connect()}>
            {t("onboarding.identityNo")}
          </Button>
        </div>
      </div>
    );
  }
  const h = health.data;
  const connected = h?.status === "ACTIVE" && channel.state !== "ONBOARDING";
  return (
    <div className="space-y-2">
      {connected && h && (
        <p className="text-sm" data-testid="connected-as">
          {t("onboarding.connectedAs", {
            handle: channel.youtube_handle ?? channel.youtube_channel_id ?? "",
          })}{" "}
          <TokenBadge channel={channel} />
          {h.expires_hint && (
            <span className="block text-xs text-muted">
              {t("onboarding.expiresHint", { when: new Date(h.expires_hint).toLocaleString() })}
            </span>
          )}
        </p>
      )}
      {(!connected || channel.oauth_expiring_soon || h?.status === "NEEDS_REAUTH") && (
        <Button
          variant="primary"
          data-testid="connect-google"
          disabled={busy || !CONNECTABLE.has(channel.state)}
          onClick={() => void connect()}
        >
          {connected ? t("onboarding.reconnect") : t("onboarding.connect")}
        </Button>
      )}
      <p className="text-xs text-muted">{t("onboarding.connectHint")}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------------- test upload
function TestUploadPanel({ channel, onDone }: { channel: ChannelOut; onDone: () => Promise<void> }) {
  const toast = useToast();
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useQuery<UploadJobOut>({
    queryKey: ["upload", jobId],
    enabled: jobId !== null,
    queryFn: () =>
      call(() => api.GET("/api/v1/uploads/{upload_id}", { params: { path: { upload_id: jobId ?? "" } } })),
    refetchInterval: (q) => (q.state.data && FINAL.has(q.state.data.state) ? false : 1500),
  });
  const ready = channel.state === "CONNECTED" || channel.state === "ACTIVE";
  const start = async () => {
    setError(null);
    try {
      const r = await call(() =>
        api.POST("/api/v1/channels/{channel_id}/test-upload", {
          params: { path: { channel_id: channel.id } },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      setJobId(r.id);
    } catch (e) {
      setError(problemText(e));
    }
  };
  const j = job.data;
  const done = j?.state === "COMPLETED";
  if (done && j.youtube_video_id && !job.isFetching) {
    void onDone();
  }
  const pct = j && j.bytes_total > 0 ? Math.round((j.bytes_confirmed / j.bytes_total) * 100) : 0;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">{t("onboarding.testUploadHint")}</p>
      <Button
        variant="primary"
        data-testid="test-upload"
        disabled={!ready || (j !== undefined && !FINAL.has(j.state))}
        onClick={() => void start().then(() => toast(t("onboarding.uploadQueued")))}
      >
        {t("actions.runTestUpload")}
      </Button>
      {!ready && <p className="text-xs text-muted">{t("onboarding.testUploadNeedsConnect")}</p>}
      {error && (
        <p role="alert" className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text">
          {error}
        </p>
      )}
      {j && (
        <div data-testid="upload-progress" className="space-y-1">
          <p className="text-sm">
            {t(`uploadStates.${j.state}`)} · {pct}%
          </p>
          <div
            role="progressbar"
            aria-label={t("onboarding.uploadProgress")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            className="h-2 overflow-hidden rounded-full bg-surface-2"
          >
            <div className="h-full bg-accent transition-all" style={{ width: `${String(pct)}%` }} />
          </div>
          {done && j.youtube_video_id && (
            <p className="text-sm text-ok-text">
              {t("onboarding.uploadDone")}{" "}
              <a
                className="underline"
                href={`https://studio.youtube.com/video/${j.youtube_video_id}/edit`}
                target="_blank"
                rel="noreferrer noopener"
              >
                {t("onboarding.openStudio")}
              </a>
            </p>
          )}
          {j.state === "FAILED" && (
            <p role="alert" className="text-sm text-danger-text">
              {j.error_class}: {j.error_detail}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------- page
function StepItem({
  index,
  step,
  channelId,
  children,
  onChanged,
}: {
  index: number;
  step: StepOut;
  channelId: string;
  children?: ReactNode;
  onChanged: () => Promise<void>;
}) {
  const toast = useToast();
  const set = async (status: StepOut["status"]) => {
    try {
      await call(() =>
        api.PATCH("/api/v1/channels/{channel_id}/onboarding/{step_code}", {
          params: { path: { channel_id: channelId, step_code: step.step_code } },
          body: { status },
        }),
      );
      await onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const done = step.status === "DONE";
  return (
    <li
      data-testid={`step-${step.step_code}`}
      className="tf-card tf-rise rounded-xl border border-line bg-surface p-5"
    >
      <div className="flex flex-wrap items-start gap-3">
        <span
          aria-hidden="true"
          className={`grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold ${
            done ? "bg-ok-soft text-ok-text" : "bg-surface-2 text-fg"
          }`}
        >
          {done ? "✓" : index + 1}
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold">{t(`onboarding.steps.${step.step_code}.title`)}</h2>
            <Badge tone={done ? "ok" : step.status === "SKIPPED" ? "neutral" : "info"}>
              {t(`onboarding.status.${step.status}`)}
            </Badge>
          </div>
          <p className="text-sm text-muted">{t(`onboarding.steps.${step.step_code}.how`)}</p>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {HELP[step.step_code].map((href) => (
              <li key={href}>
                <a className="text-accent underline" href={href} target="_blank" rel="noreferrer noopener">
                  {new URL(href).hostname}
                  <span className="sr-only"> {t("onboarding.opensNewTab")}</span>
                </a>
              </li>
            ))}
          </ul>
          {children}
          {!step.system && (
            <div className="flex flex-wrap gap-2 pt-1">
              {!done && <Button onClick={() => void set("DONE")}>{t("actions.markDone")}</Button>}
              {step.status === "TODO" && (
                <Button onClick={() => void set("SKIPPED")}>{t("onboarding.skip")}</Button>
              )}
              {step.status !== "TODO" && (
                <Button onClick={() => void set("TODO")}>{t("onboarding.undo")}</Button>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

/** Page 4 — Channel Onboarding (real API since Phase 4). */
export function OnboardingPage() {
  const page = getPage("onboarding");
  const { id = "" } = useParams();
  const { channel, steps } = useChannelData(id);
  const refresh = useRefresh(id);
  const toast = useToast();
  const command = async (cmd: "start-onboarding" | "reconnect") => {
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/commands/{cmd}", {
          params: { path: { channel_id: id, cmd } },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      await refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const list = steps.data ?? [];
  const doneCount = list.filter((s) => s.status !== "TODO").length;
  const ch = channel.data;
  return (
    <div className="space-y-4" data-testid="page-onboarding">
      <PageTitle page={page}>
        {ch && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold" dir="auto">
              {ch.name}
            </span>
            <StateBadge state={ch.state} />
          </div>
        )}
      </PageTitle>
      {(steps.isPending || channel.isPending) && <LoadingSkeleton />}
      {(steps.isError || channel.isError) && (
        <ProblemDisplay
          problem={asProblem(steps.error ?? channel.error)}
          onRetry={() => void Promise.all([steps.refetch(), channel.refetch()])}
        />
      )}
      {ch && steps.data && (
        <div data-testid="state-success" className="space-y-4">
          {(ch.state === "APPROVED" || ch.state === "DISCONNECTED") && (
            <Card>
              <p className="mb-3 text-sm">
                {t(ch.state === "APPROVED" ? "onboarding.startHint" : "onboarding.reconnectHint")}
              </p>
              <Button
                variant="primary"
                onClick={() => void command(ch.state === "APPROVED" ? "start-onboarding" : "reconnect")}
              >
                {t(ch.state === "APPROVED" ? "onboarding.start" : "onboarding.reconnectChannel")}
              </Button>
            </Card>
          )}
          <div className="tf-card rounded-xl border border-line bg-surface p-4">
            <p className="text-sm font-medium">
              {t("onboarding.progress", { done: doneCount, total: list.length })}
            </p>
            <div
              role="progressbar"
              aria-label={t("onboarding.progressLabel")}
              aria-valuemin={0}
              aria-valuemax={list.length}
              aria-valuenow={doneCount}
              className="mt-2 h-2 overflow-hidden rounded-full bg-surface-2"
            >
              <div
                className="h-full bg-accent transition-all"
                style={{ width: `${String(list.length ? (doneCount / list.length) * 100 : 0)}%` }}
              />
            </div>
          </div>
          <ol className="space-y-3" aria-label={t("onboarding.stepsLabel")}>
            {list.map((s, i) => (
              <StepItem key={s.step_code} index={i} step={s} channelId={id} onChanged={refresh}>
                {s.step_code === "OAUTH_CLIENT" && <OAuthClientPanel onSaved={refresh} />}
                {s.step_code === "PRIVACY_POLICY" && <PrivacyPanel channel={ch} onSaved={refresh} />}
                {s.step_code === "CONNECT" && ch.state !== "APPROVED" && (
                  <ConnectPanel channel={ch} onDone={refresh} />
                )}
                {s.step_code === "TEST_UPLOAD" && <TestUploadPanel channel={ch} onDone={refresh} />}
              </StepItem>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
