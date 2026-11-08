import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { useToast } from "../components/Toasts";
import { Badge, Button, Card } from "../components/ui";
import { t } from "../i18n";
import { api, call, ProblemError, type SettingsOut } from "../lib/api/client";
import { useMe } from "../lib/useBackend";
import { asProblem, LoadingSkeleton, PageTitle } from "./PageView";
import { getPage } from "./registry";

const inputCls = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2";
const time = z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/, "Use HH:MM");

const settingsSchema = z.object({
  night_render_start: time,
  night_render_end: time,
  quiet_hours_start: time,
  quiet_hours_end: time,
  owner_timezone: z.string().min(1).max(64),
  disk_budget_gb: z.coerce.number().int().min(10).max(100000),
});
type SettingsForm = z.infer<typeof settingsSchema>;

const hhmm = (v: string) => v.slice(0, 5);

function GeneralSettings({ data }: { data: SettingsOut }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [conflict, setConflict] = useState(false);
  const { register, handleSubmit, reset, formState } = useForm<SettingsForm>({
    resolver: zodResolver(settingsSchema) as never,
    defaultValues: {},
  });
  useEffect(() => {
    reset({
      night_render_start: hhmm(data.night_render_start),
      night_render_end: hhmm(data.night_render_end),
      quiet_hours_start: hhmm(data.quiet_hours_start),
      quiet_hours_end: hhmm(data.quiet_hours_end),
      owner_timezone: data.owner_timezone,
      disk_budget_gb: data.disk_budget_gb,
    });
  }, [data, reset]);
  const save = handleSubmit(async (values) => {
    setConflict(false);
    try {
      const next = await call(() =>
        api.PUT("/api/v1/settings", {
          body: { ...values, settings: data.settings },
          headers: { "If-Match": `"${String(data.version)}"` },
        }),
      );
      qc.setQueryData(["page", "settings"], next);
      toast(t("settingsPage.saved"));
    } catch (e) {
      if (e instanceof ProblemError && e.problem.code === "VERSION_CONFLICT") setConflict(true);
      else
        toast(
          e instanceof ProblemError ? (e.problem.detail ?? e.problem.title) : t("states.errorTitle"),
          "danger",
        );
    }
  });
  const field = (name: keyof SettingsForm, label: string, type = "time") => (
    <div>
      <label htmlFor={`set-${name}`} className="block text-sm font-medium">
        {label}
      </label>
      <input id={`set-${name}`} type={type} className={inputCls} {...register(name)} />
      {formState.errors[name] && (
        <p role="alert" className="mt-1 text-sm text-danger-text">
          {formState.errors[name]?.message}
        </p>
      )}
    </div>
  );
  return (
    <Card title={t("settingsPage.general")}>
      <form onSubmit={(e) => void save(e)} noValidate data-testid="settings-form" className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {field("night_render_start", t("settingsPage.nightStart"))}
          {field("night_render_end", t("settingsPage.nightEnd"))}
          {field("quiet_hours_start", t("settingsPage.quietStart"))}
          {field("quiet_hours_end", t("settingsPage.quietEnd"))}
          {field("owner_timezone", t("settingsPage.timezone"), "text")}
          {field("disk_budget_gb", t("settingsPage.disk"), "number")}
        </div>
        {conflict && (
          <p role="alert" className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text">
            {t("settingsPage.conflict")}{" "}
            <button
              type="button"
              className="underline"
              onClick={() => void qc.invalidateQueries({ queryKey: ["page", "settings"] })}
            >
              {t("settingsPage.reload")}
            </button>
          </p>
        )}
        <Button type="submit" variant="primary" disabled={formState.isSubmitting}>
          {t("actions.save")}
        </Button>
      </form>
    </Card>
  );
}

function TwoFactor() {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const [enrol, setEnrol] = useState<{ uri: string; svg: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const enabled = me.data?.mfa_enabled ?? false;
  const start = useMutation({
    mutationFn: () => call(() => api.POST("/api/v1/auth/mfa/enroll")),
    onSuccess: (r) => setEnrol({ uri: r.otpauth_uri, svg: r.qr_svg }),
  });
  const confirm = async () => {
    setError(null);
    try {
      const r = await call(() => api.POST("/api/v1/auth/mfa/confirm", { body: { code } }));
      setCodes(r.recovery_codes);
      setEnrol(null);
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (e) {
      setError(e instanceof ProblemError ? (e.problem.detail ?? e.problem.title) : t("states.errorTitle"));
    }
  };
  const disable = async () => {
    await call(() => api.DELETE("/api/v1/auth/mfa"));
    await qc.invalidateQueries({ queryKey: ["me"] });
    toast(t("settingsPage.mfaDisabled"));
  };
  return (
    <Card title={t("settingsPage.mfa")}>
      <p className="text-sm">
        {enabled ? (
          <Badge tone="ok">{t("settingsPage.mfaOn")}</Badge>
        ) : (
          <Badge tone="warn">{t("settingsPage.mfaOff")}</Badge>
        )}
      </p>
      <p className="mt-2 text-sm text-muted">{t("settingsPage.mfaHelp")}</p>
      {!enabled && !enrol && !codes && (
        <Button className="mt-3" variant="primary" onClick={() => start.mutate()} data-testid="mfa-start">
          {t("actions.enrolTotp")}
        </Button>
      )}
      {start.isError && <ProblemDisplay problem={asProblem(start.error)} />}
      {enrol && (
        <div className="mt-4 space-y-3" data-testid="mfa-enrol">
          <p className="text-sm">{t("settingsPage.mfaScan")}</p>
          <div
            className="inline-block rounded-lg bg-white p-2"
            role="img"
            aria-label={t("settingsPage.mfaQr")}
            // The SVG is generated by the server from our own otpauth URI (no user content).
            dangerouslySetInnerHTML={{ __html: enrol.svg }}
          />
          <details className="text-xs text-muted">
            <summary className="cursor-pointer">{t("settingsPage.mfaManual")}</summary>
            <code className="break-all">{enrol.uri}</code>
          </details>
          <label htmlFor="mfa-confirm-code" className="block text-sm font-medium">
            {t("login.code")}
          </label>
          <input
            id="mfa-confirm-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className={inputCls + " max-w-48"}
          />
          {error && (
            <p role="alert" className="text-sm text-danger-text">
              {error}
            </p>
          )}
          <Button variant="primary" onClick={() => void confirm()}>
            {t("settingsPage.mfaConfirm")}
          </Button>
        </div>
      )}
      {codes && (
        <div
          className="mt-4 rounded-lg border border-warn-text/40 bg-warn-soft p-4 text-warn-text"
          data-testid="recovery-codes"
        >
          <p className="font-semibold">{t("settingsPage.recoveryTitle")}</p>
          <p className="mt-1 text-sm">{t("settingsPage.recoveryHelp")}</p>
          <ul className="mt-2 grid grid-cols-2 gap-1 font-mono text-sm">
            {codes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {enabled && (
        <Button className="mt-3" variant="danger" onClick={() => void disable()}>
          {t("settingsPage.mfaDisable")}
        </Button>
      )}
    </Card>
  );
}

const passwordSchema = z.object({
  current: z.string().min(1),
  new: z.string().min(12, t("settingsPage.passwordShort")),
});

function ChangePassword() {
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, reset, formState } = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
  });
  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      await call(() => api.POST("/api/v1/auth/password", { body: values }));
      reset({ current: "", new: "" });
      toast(t("settingsPage.passwordChanged"));
    } catch (e) {
      setError(e instanceof ProblemError ? (e.problem.detail ?? e.problem.title) : t("states.errorTitle"));
    }
  });
  return (
    <Card title={t("settingsPage.password")}>
      <form onSubmit={(e) => void submit(e)} noValidate className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="pw-current" className="block text-sm font-medium">
            {t("settingsPage.currentPassword")}
          </label>
          <input
            id="pw-current"
            type="password"
            autoComplete="current-password"
            className={inputCls}
            {...register("current")}
          />
        </div>
        <div>
          <label htmlFor="pw-new" className="block text-sm font-medium">
            {t("settingsPage.newPassword")}
          </label>
          <input
            id="pw-new"
            type="password"
            autoComplete="new-password"
            className={inputCls}
            {...register("new")}
          />
          {formState.errors.new && (
            <p role="alert" className="mt-1 text-sm text-danger-text">
              {formState.errors.new.message}
            </p>
          )}
        </div>
        {error && (
          <p role="alert" className="text-sm text-danger-text sm:col-span-2">
            {error}
          </p>
        )}
        <div className="sm:col-span-2">
          <Button type="submit" disabled={formState.isSubmitting}>
            {t("settingsPage.changePassword")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Sessions() {
  const qc = useQueryClient();
  const sessions = useQuery({
    queryKey: ["page", "settings", "sessions"],
    queryFn: () => call(() => api.GET("/api/v1/auth/sessions")),
  });
  const revoke = async (id: string) => {
    await call(() =>
      api.DELETE("/api/v1/auth/sessions/{session_id}", { params: { path: { session_id: id } } }),
    );
    await qc.invalidateQueries({ queryKey: ["page", "settings", "sessions"] });
  };
  return (
    <Card title={t("settingsPage.sessions")}>
      <ul className="divide-y divide-line">
        {(sessions.data ?? []).map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
            <span className="min-w-0">
              <span className="block truncate font-medium">{s.user_agent ?? "—"}</span>
              <span className="text-xs text-muted">
                {t("settingsPage.lastSeen", { when: new Date(s.last_seen_at).toLocaleString("en-GB") })}
              </span>
            </span>
            {s.current ? (
              <Badge tone="info">{t("settingsPage.thisSession")}</Badge>
            ) : (
              <Button onClick={() => void revoke(s.id)}>{t("actions.revokeSession")}</Button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Page 31 — Settings & Integrations (real system settings, 2FA, password, sessions since Phase 3). */
export function SettingsPage() {
  const page = getPage("settings");
  const query = useQuery({
    queryKey: ["page", "settings"],
    queryFn: () => call(() => api.GET("/api/v1/settings")),
  });
  return (
    <div className="space-y-4" data-testid="page-settings">
      <PageTitle page={page} />
      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {query.data && (
        <div data-testid="state-success" className="grid gap-4 xl:grid-cols-2">
          <GeneralSettings data={query.data} />
          <TwoFactor />
          <ChangePassword />
          <Sessions />
        </div>
      )}
    </div>
  );
}
