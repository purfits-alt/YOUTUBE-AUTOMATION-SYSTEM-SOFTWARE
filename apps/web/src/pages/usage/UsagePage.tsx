import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Meter } from "../../components/Meter";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type ProviderOut, type UsageLine } from "../../lib/api/client";
import { useQuota } from "../../lib/useBackend";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";

const TIER_TONE: Record<ProviderOut["tier"], Tone> = { L: "ok", F: "info", P: "warn" };
const money = (minor: number) =>
  (minor / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
const enc = (code: string) => code; // openapi-fetch encodes the path parameter

function limitOf(p: ProviderOut, metric: string): number | null {
  return p.limits.find((l) => l.metric === metric && l.period === "DAY")?.limit_value ?? null;
}

function KeyForm({ provider, onSaved }: { provider: ProviderOut; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [secret, setSecret] = useState("");
  const id = `key-${provider.family}`;
  const save = async () => {
    try {
      await call(() =>
        api.PUT("/api/v1/providers/{code}/credentials", {
          params: { path: { code: enc(provider.code) } },
          body: { secret },
        }),
      );
      setSecret("");
      toast(t("usagePage.keySaved", { family: provider.family }));
      await onSaved();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <div className="flex flex-wrap items-end gap-2" data-testid={`key-form-${provider.family}`}>
      <div className="min-w-0 flex-1">
        <label htmlFor={id} className="block text-sm font-medium">
          {t("usagePage.apiKey", { family: provider.family })}
        </label>
        <input
          id={id}
          type="password"
          autoComplete="off"
          className={inputCls}
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
        />
      </div>
      <Button variant="primary" disabled={secret.trim().length < 8} onClick={() => void save()}>
        {t("usagePage.saveKey")}
      </Button>
    </div>
  );
}

function ModelRow({
  p,
  usage,
  onChanged,
}: {
  p: ProviderOut;
  usage: UsageLine[];
  onChanged: () => Promise<void>;
}) {
  const toast = useToast();
  const [rpd, setRpd] = useState(String(limitOf(p, "REQUESTS") ?? ""));
  const [tpd, setTpd] = useState(String(limitOf(p, "TOKENS") ?? ""));
  const used = (metric: string) =>
    usage.find((u) => u.provider_code === p.code && u.metric === metric)?.used ?? 0;
  const patch = async (body: Record<string, unknown>, done: string) => {
    try {
      const r = await call(() =>
        api.PATCH("/api/v1/providers/{code}", { params: { path: { code: enc(p.code) } }, body }),
      );
      toast(r.warnings[0] ?? done);
      await onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const saveLimits = () => {
    const limits = [
      ...(rpd.trim()
        ? [{ metric: "REQUESTS" as const, period: "DAY" as const, limit_value: Number(rpd) }]
        : []),
      ...(tpd.trim()
        ? [{ metric: "TOKENS" as const, period: "DAY" as const, limit_value: Number(tpd) }]
        : []),
    ];
    void patch({ limits }, t("usagePage.limitsSaved"));
  };
  const verify = async () => {
    try {
      await call(() =>
        api.POST("/api/v1/providers/{code}/verify", {
          params: { path: { code: enc(p.code) } },
          body: { verified_url: p.verified_url },
        }),
      );
      await onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const ids = (s: string) => `${s}-${p.code.replace(/[^a-z0-9]/gi, "-")}`;
  return (
    <li className="space-y-3 rounded-xl border border-line p-4" data-testid={`provider-${p.code}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold break-all">{p.code.split(":").slice(1).join(":")}</p>
          <p className="text-xs text-muted">
            {p.licence} · {t(`usagePage.commercial.${p.commercial_use}`)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={TIER_TONE[p.tier]}>{t(`usagePage.tier.${p.tier}`)}</Badge>
          {p.data_use_training !== false && p.tier !== "L" && (
            <Badge tone="warn">{t("usagePage.mayTrain")}</Badge>
          )}
          {p.reverify_due && <Badge tone="warn">{t("usagePage.reverifyDue")}</Badge>}
          <label className="ms-2 flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={p.enabled}
              onChange={(e) =>
                void patch(
                  { enabled: e.target.checked },
                  t(e.target.checked ? "usagePage.enabledToast" : "usagePage.disabledToast"),
                )
              }
            />
            {t("usagePage.enabled")}
          </label>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Meter
          label={t("usagePage.requestsToday")}
          value={used("REQUESTS")}
          max={limitOf(p, "REQUESTS")}
          testId={ids("meter-req")}
        />
        <Meter label={t("usagePage.tokensToday")} value={used("TOKENS")} max={limitOf(p, "TOKENS")} />
      </div>
      {p.tier !== "L" && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor={ids("rpd")} className="block text-xs font-medium">
              {t("usagePage.rpd")}
            </label>
            <input
              id={ids("rpd")}
              type="number"
              min={0}
              className={`${inputCls} w-36`}
              value={rpd}
              onChange={(e) => setRpd(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor={ids("tpd")} className="block text-xs font-medium">
              {t("usagePage.tpd")}
            </label>
            <input
              id={ids("tpd")}
              type="number"
              min={0}
              className={`${inputCls} w-40`}
              value={tpd}
              onChange={(e) => setTpd(e.target.value)}
            />
          </div>
          <Button onClick={saveLimits}>{t("actions.setLimits")}</Button>
          {p.published_limits.placeholder === true && (
            <span className="text-xs text-warn-text">{t("usagePage.placeholder")}</span>
          )}
        </div>
      )}
      <p className="text-xs text-muted">
        {t("usagePage.verified", { date: p.verified_at })}{" "}
        <a className="text-accent underline" href={p.verified_url} target="_blank" rel="noreferrer noopener">
          {t("usagePage.source")}
        </a>{" "}
        <button type="button" className="text-accent underline" onClick={() => void verify()}>
          {t("usagePage.markVerified")}
        </button>
      </p>
    </li>
  );
}

function PaidCard({ p, onChanged }: { p: ProviderOut; onChanged: () => Promise<void> }) {
  const toast = useToast();
  const [ack, setAck] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [cap, setCap] = useState("");
  const [step1, setStep1] = useState<{ phrase: string; at: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!step1) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [step1]);
  const wait = step1 ? Math.max(0, Math.ceil((step1.at - now) / 1000)) : 0;
  const doStep1 = async () => {
    try {
      const r = await call(() =>
        api.POST("/api/v1/providers/{code}/paid-activation/step1", {
          params: { path: { code: enc(p.code) } },
          body: { acknowledge_cost: true },
        }),
      );
      setStep1({ phrase: r.confirm_phrase, at: new Date(r.earliest_step2_at).getTime() });
      await onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const doStep2 = async () => {
    try {
      await call(() =>
        api.POST("/api/v1/providers/{code}/paid-activation/step2", {
          params: { path: { code: enc(p.code) } },
          body: { confirm_phrase: phrase, monthly_cap_minor: Math.round(Number(cap) * 100) },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      setStep1(null);
      toast(t("usagePage.paidEnabled"));
      await onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const disable = async () => {
    await call(() =>
      api.POST("/api/v1/providers/{code}/paid-activation/disable", {
        params: { path: { code: enc(p.code) } },
      }),
    );
    setStep1(null);
    await onChanged();
  };
  return (
    <li className="space-y-3 rounded-xl border border-warn-text p-4" data-testid={`paid-${p.code}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold break-all">{p.code}</p>
        <Badge tone={p.enabled ? "danger" : "neutral"}>
          {p.enabled ? t("usagePage.paidOn") : t("usagePage.paidStep", { step: p.paid_activation_step })}
        </Badge>
      </div>
      <p className="text-sm text-muted">{p.notes}</p>
      {p.enabled ? (
        <Button onClick={() => void disable()}>{t("usagePage.disablePaid")}</Button>
      ) : !step1 ? (
        <div className="space-y-2">
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            {t("usagePage.ackCost")}
          </label>
          <Button disabled={!ack} onClick={() => void doStep1()}>
            {t("usagePage.step1")}
          </Button>
        </div>
      ) : (
        <div className="space-y-2" data-testid="paid-step2">
          <p className="text-sm">{t("usagePage.typePhrase", { phrase: step1.phrase })}</p>
          <label htmlFor="paid-phrase" className="sr-only">
            {t("usagePage.phraseLabel")}
          </label>
          <input
            id="paid-phrase"
            className={inputCls}
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
          />
          <label htmlFor="paid-cap" className="block text-sm font-medium">
            {t("usagePage.monthlyCap")}
          </label>
          <input
            id="paid-cap"
            type="number"
            min={0.01}
            step={0.01}
            className={`${inputCls} w-40`}
            value={cap}
            onChange={(e) => setCap(e.target.value)}
          />
          <Button
            variant="danger"
            disabled={wait > 0 || !phrase || !(Number(cap) > 0)}
            onClick={() => void doStep2()}
          >
            {wait > 0 ? t("usagePage.waitSeconds", { s: wait }) : t("usagePage.step2")}
          </Button>
        </div>
      )}
    </li>
  );
}

function Budgets() {
  const qc = useQueryClient();
  const toast = useToast();
  const budgets = useQuery({ queryKey: ["budgets"], queryFn: () => call(() => api.GET("/api/v1/budgets")) });
  const stock = budgets.data?.find((b) => b.scope === "STOCK");
  const [cap, setCap] = useState("");
  const save = async () => {
    try {
      await call(() =>
        api.PUT("/api/v1/budgets", { body: { scope: "STOCK", cap_minor: Math.round(Number(cap) * 100) } }),
      );
      setCap("");
      await qc.invalidateQueries({ queryKey: ["budgets"] });
      toast(t("usagePage.budgetSaved"));
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <Card title={t("usagePage.budgets")}>
      <ul className="space-y-2 text-sm">
        {(budgets.data ?? []).map((b) => (
          <li key={`${b.scope}-${b.provider_code ?? ""}`}>
            <Meter
              label={`${t(`usagePage.budgetScope.${b.scope}`)}${b.provider_code ? ` · ${b.provider_code}` : ""}`}
              value={b.spent_minor}
              max={b.cap_minor}
            />
          </li>
        ))}
      </ul>
      <p className="mt-2 text-sm text-muted">
        {t("usagePage.stockCap", { cap: money(stock?.cap_minor ?? 0) })}
      </p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="stock-cap" className="block text-xs font-medium">
            {t("usagePage.newStockCap")}
          </label>
          <input
            id="stock-cap"
            type="number"
            min={0}
            step={0.01}
            className={`${inputCls} w-40`}
            value={cap}
            onChange={(e) => setCap(e.target.value)}
          />
        </div>
        <Button disabled={cap.trim() === ""} onClick={() => void save()}>
          {t("actions.setBudget")}
        </Button>
      </div>
    </Card>
  );
}

/** Page 26 — Cost & Usage Manager (real API since Phase 5). */
export function UsagePage() {
  const page = getPage("usage");
  const qc = useQueryClient();
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => call(() => api.GET("/api/v1/providers")),
  });
  const usage = useQuery({
    queryKey: ["usage", "day"],
    queryFn: () => call(() => api.GET("/api/v1/usage", { params: { query: { period: "day" } } })),
    refetchInterval: 30_000,
  });
  const summary = useQuery({
    queryKey: ["cost-summary"],
    queryFn: () => call(() => api.GET("/api/v1/costs/summary")),
  });
  const quota = useQuota();
  const refresh = async () => {
    await Promise.all(
      ["providers", "usage", "cost-summary", "budgets"].map((k) => qc.invalidateQueries({ queryKey: [k] })),
    );
  };
  const list = providers.data ?? [];
  const free = list.filter((p) => p.tier !== "P");
  const paidList = list.filter((p) => p.tier === "P");
  const families = [...new Set(free.map((p) => p.family))];
  const s = summary.data;
  const zero = s ? s.spent_minor === 0 && s.paid_enabled.length === 0 : true;
  return (
    <div className="space-y-4" data-testid="page-usage">
      <PageTitle page={page} />
      {s && (
        <p
          data-testid="cost-banner"
          className={`tf-rise rounded-xl px-4 py-3 text-sm font-medium ${zero ? "bg-ok-soft text-ok-text" : "bg-warn-soft text-warn-text"}`}
        >
          {t("usagePage.banner", { spent: money(s.spent_minor), count: s.paid_enabled.length })}
        </p>
      )}
      {providers.isPending && <LoadingSkeleton />}
      {providers.isError && (
        <ProblemDisplay problem={asProblem(providers.error)} onRetry={() => void providers.refetch()} />
      )}
      {providers.data && list.length === 0 && (
        <StateCard
          message={t("pages.usage.empty")}
          actionLabel={t("pages.usage.emptyAction")}
          onAction={() => void providers.refetch()}
        />
      )}
      {list.length > 0 && (
        <div data-testid="state-success" className="space-y-4">
          {families.map((fam) => {
            const models = free.filter((p) => p.family === fam);
            const first = models[0];
            return (
              <Card key={fam} title={t(`usagePage.family.${fam}`)}>
                <div className="space-y-4">
                  <p className="text-sm text-muted">{t(`usagePage.familyHint.${fam}`)}</p>
                  {first?.needs_key &&
                    (first.has_key ? (
                      <p className="text-sm" data-testid={`key-set-${fam}`}>
                        <Badge tone="ok">{t("usagePage.keySet")}</Badge>{" "}
                        <button
                          type="button"
                          className="text-accent underline"
                          onClick={() =>
                            void call(() =>
                              api.DELETE("/api/v1/providers/{code}/credentials", {
                                params: { path: { code: first.code } },
                              }),
                            ).then(refresh)
                          }
                        >
                          {t("usagePage.removeKey")}
                        </button>
                      </p>
                    ) : (
                      first && <KeyForm provider={first} onSaved={refresh} />
                    ))}
                  <ul className="space-y-3">
                    {models.map((p) => (
                      <ModelRow key={p.code} p={p} usage={usage.data ?? []} onChanged={refresh} />
                    ))}
                  </ul>
                </div>
              </Card>
            );
          })}
          {paidList.length > 0 && (
            <Card title={t("usagePage.paidTitle")}>
              <p className="mb-3 text-sm text-muted">{t("usagePage.paidHint")}</p>
              <ul className="space-y-3">
                {paidList.map((p) => (
                  <PaidCard key={p.code} p={p} onChanged={refresh} />
                ))}
              </ul>
            </Card>
          )}
          <Card title={t("usagePage.youtube")}>
            <div className="space-y-3">
              {(quota.data ?? []).flatMap((q) =>
                q.buckets.map((b) => (
                  <Meter
                    key={`${q.gcp_project}-${b.bucket}`}
                    label={`${b.bucket} · ${q.gcp_project} · ${t("usagePage.resets", { at: b.resets_at_pkt })}`}
                    value={b.used + b.held}
                    max={b.usable}
                  />
                )),
              )}
            </div>
          </Card>
          <Budgets />
        </div>
      )}
    </div>
  );
}
