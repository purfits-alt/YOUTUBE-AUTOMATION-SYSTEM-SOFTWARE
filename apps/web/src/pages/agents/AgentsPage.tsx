import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Dialog } from "../../components/Dialog";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StatTile } from "../../components/StatTile";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type AgentOut, type AgentRunOut } from "../../lib/api/client";
import { useControls } from "../../lib/useBackend";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";

const RUN_TONE: Record<AgentRunOut["status"], Tone> = {
  RUNNING: "info",
  SUCCEEDED: "ok",
  REPAIRED: "ok",
  FAILED: "danger",
  ABORTED: "neutral",
  WAITING_QUOTA: "warn",
};
const short = (code: string) => code.split(":").slice(1).join(":") || code;

function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: () => call(() => api.GET("/api/v1/providers")) });
}

function AgentStatus({ a }: { a: AgentOut }) {
  if (a.paused) return <Badge tone="warn">{t("agentsPage.paused")}</Badge>;
  if (!a.enabled) return <Badge tone="neutral">{t("agentsPage.disabled")}</Badge>;
  return <Badge tone="ok">{t("agentsPage.enabled")}</Badge>;
}

function ConfigDialog({ agent, onClose }: { agent: AgentOut; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const providers = useProviders();
  const llm = (providers.data ?? []).filter((p) => p.capability === "LLM");
  const [enabled, setEnabled] = useState(agent.enabled);
  const [chain, setChain] = useState<string[]>(agent.provider_chain);
  const [calls, setCalls] = useState(String(agent.limits.calls_per_day ?? ""));
  const [tokens, setTokens] = useState(String(agent.limits.tokens_per_day ?? ""));
  const [error, setError] = useState<string | null>(null);
  const move = (i: number, d: number) => {
    const next = [...chain];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j] ?? "", next[i] ?? ""];
    setChain(next);
  };
  const save = async () => {
    setError(null);
    const num = (v: string) => (v.trim() === "" ? null : Number(v));
    try {
      await call(() =>
        api.PATCH("/api/v1/agents/{code}", {
          params: { path: { code: agent.agent_code } },
          body: {
            ...(agent.is_auditor ? {} : { enabled }),
            ...(agent.provider_chain.length || chain.length ? { provider_chain: chain } : {}),
            limits: { calls_per_day: num(calls), tokens_per_day: num(tokens) },
          },
          headers: { "If-Match": `"${agent.etag}"` },
        }),
      );
      await qc.invalidateQueries({ queryKey: ["agents"] });
      toast(t("agentsPage.saved", { name: agent.name }));
      onClose();
    } catch (e) {
      setError(problemText(e));
    }
  };
  return (
    <Dialog
      open
      title={t("agentsPage.configure", { name: agent.name })}
      onClose={onClose}
      testId="agent-config-dialog"
    >
      <div className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            disabled={agent.is_auditor}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {t("agentsPage.enabledLabel")}
        </label>
        {agent.is_auditor && <p className="text-xs text-muted">{t("agentsPage.auditorNote")}</p>}
        {agent.kind !== "DETERMINISTIC" && (
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">{t("agentsPage.chain")}</legend>
            <ol className="space-y-1" data-testid="chain-list">
              {chain.map((code, i) => (
                <li
                  key={code}
                  className="flex items-center gap-2 rounded-lg border border-line px-2 py-1 text-sm"
                >
                  <span className="w-5 text-muted">{i + 1}.</span>
                  <span className="flex-1 break-all">{code}</span>
                  <Button aria-label={t("agentsPage.up", { code })} onClick={() => move(i, -1)}>
                    ↑
                  </Button>
                  <Button aria-label={t("agentsPage.down", { code })} onClick={() => move(i, 1)}>
                    ↓
                  </Button>
                  <Button
                    aria-label={t("agentsPage.remove", { code })}
                    onClick={() => setChain(chain.filter((c) => c !== code))}
                  >
                    ✕
                  </Button>
                </li>
              ))}
            </ol>
            <label htmlFor="chain-add" className="sr-only">
              {t("agentsPage.addProvider")}
            </label>
            <select
              id="chain-add"
              className={inputCls}
              value=""
              onChange={(e) => e.target.value && setChain([...chain, e.target.value])}
            >
              <option value="">{t("agentsPage.addProvider")}</option>
              {llm
                .filter((p) => !chain.includes(p.code))
                .map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.code} ({t(`usagePage.tier.${p.tier}`)})
                  </option>
                ))}
            </select>
          </fieldset>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="lim-calls" className="block text-sm font-medium">
              {t("agentsPage.callsPerDay")}
            </label>
            <input
              id="lim-calls"
              type="number"
              min={0}
              className={inputCls}
              value={calls}
              onChange={(e) => setCalls(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="lim-tokens" className="block text-sm font-medium">
              {t("agentsPage.tokensPerDay")}
            </label>
            <input
              id="lim-tokens"
              type="number"
              min={0}
              className={inputCls}
              value={tokens}
              onChange={(e) => setTokens(e.target.value)}
            />
          </div>
        </div>
        {error && (
          <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-text">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" onClick={() => void save()}>
            {t("actions.saveConfig")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function TestRunDialog({ agent, onClose }: { agent: AgentOut; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setError(null);
    try {
      await call(() =>
        api.POST("/api/v1/agents/{code}/run", {
          params: { path: { code: agent.agent_code } },
          body: { input: { name } },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      toast(t("agentsPage.queued"));
      await qc.invalidateQueries({ queryKey: ["agent-runs"] });
      onClose();
    } catch (e) {
      setError(problemText(e));
    }
  };
  return (
    <Dialog
      open
      title={t("agentsPage.testRunTitle", { name: agent.name })}
      onClose={onClose}
      testId="agent-run-dialog"
    >
      <p className="text-sm text-muted">{t("agentsPage.testRunHint")}</p>
      <label htmlFor="hello-name" className="mt-3 block text-sm font-medium">
        {t("agentsPage.helloName")}
      </label>
      <input
        id="hello-name"
        className={inputCls}
        maxLength={80}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      {error && (
        <p role="alert" className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-text">
          {error}
        </p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onClose}>{t("confirm.cancel")}</Button>
        <Button variant="primary" disabled={!name.trim()} onClick={() => void run()}>
          {t("agentsPage.run")}
        </Button>
      </div>
    </Dialog>
  );
}

function RunDetails({ run, onClose }: { run: AgentRunOut; onClose: () => void }) {
  return (
    <Dialog
      open
      title={t("agentsPage.runTitle", { agent: run.agent_code })}
      onClose={onClose}
      testId="agent-run-details"
    >
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted">{t("columns.status")}</dt>
        <dd>{t(`agentsPage.runStatus.${run.status}`)}</dd>
        <dt className="text-muted">{t("columns.provider")}</dt>
        <dd className="break-all">{run.provider_code ?? "—"}</dd>
        <dt className="text-muted">{t("columns.tokens")}</dt>
        <dd>{(run.tokens_in ?? 0) + (run.tokens_out ?? 0)}</dd>
      </dl>
      {run.error_detail && (
        <p className="mt-3 rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text">
          {run.error_class}: {run.error_detail}
        </p>
      )}
      <h3 className="mt-4 text-sm font-semibold">{t("agentsPage.input")}</h3>
      <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-surface-2 p-2 text-xs" tabIndex={0}>
        {JSON.stringify(run.input, null, 2)}
      </pre>
      <h3 className="mt-3 text-sm font-semibold">{t("agentsPage.output")}</h3>
      <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-surface-2 p-2 text-xs" tabIndex={0}>
        {run.output ? JSON.stringify(run.output, null, 2) : "—"}
      </pre>
    </Dialog>
  );
}

function RecentRuns() {
  const runs = useQuery({
    queryKey: ["agent-runs"],
    queryFn: () => call(() => api.GET("/api/v1/agent-runs", { params: { query: { limit: 20 } } })),
    refetchInterval: 5000,
  });
  const [open, setOpen] = useState<AgentRunOut | null>(null);
  const items = runs.data?.items ?? [];
  return (
    <Card title={t("agentsPage.recentRuns")}>
      {runs.isError && <ProblemDisplay problem={asProblem(runs.error)} onRetry={() => void runs.refetch()} />}
      {runs.data && items.length === 0 && (
        <p className="text-sm text-muted" data-testid="runs-empty">
          {t("agentsPage.noRuns")}
        </p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={t("agentsPage.recentRuns")}>
          <table className="w-full text-sm" data-testid="runs-table">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="py-2 pe-3 font-medium">{t("columns.time")}</th>
                <th className="py-2 pe-3 font-medium">{t("columns.agent")}</th>
                <th className="py-2 pe-3 font-medium">{t("columns.status")}</th>
                <th className="py-2 pe-3 font-medium">{t("columns.provider")}</th>
                <th className="py-2 pe-3 font-medium">{t("columns.tokens")}</th>
                <th className="py-2 pe-3 font-medium">{t("columns.duration")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-t border-line">
                  <td className="py-2 pe-3 whitespace-nowrap">
                    <button type="button" className="text-accent underline" onClick={() => setOpen(r)}>
                      {new Date(r.started_at).toLocaleTimeString()}
                    </button>
                  </td>
                  <td className="py-2 pe-3">{r.agent_code}</td>
                  <td className="py-2 pe-3">
                    <Badge tone={RUN_TONE[r.status]}>{t(`agentsPage.runStatus.${r.status}`)}</Badge>
                  </td>
                  <td className="py-2 pe-3 break-all">{r.provider_code ? short(r.provider_code) : "—"}</td>
                  <td className="py-2 pe-3 tabular-nums">{(r.tokens_in ?? 0) + (r.tokens_out ?? 0)}</td>
                  <td className="py-2 pe-3 tabular-nums">
                    {r.duration_ms === null ? "—" : `${String(r.duration_ms)} ms`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && <RunDetails run={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

/** Page 28 — AI Agent Control Center (real API since Phase 5). */
export function AgentsPage() {
  const page = getPage("agents");
  const qc = useQueryClient();
  const toast = useToast();
  const controls = useControls();
  const agents = useQuery({ queryKey: ["agents"], queryFn: () => call(() => api.GET("/api/v1/agents")) });
  const [config, setConfig] = useState<AgentOut | null>(null);
  const [testRun, setTestRun] = useState<AgentOut | null>(null);
  const list = agents.data ?? [];
  const pause = async (a: AgentOut) => {
    try {
      if (a.paused) {
        const sw = controls.data?.kill_switches.find(
          (k) => k.scope === "AGENT" && k.target_id === a.agent_code,
        );
        if (sw)
          await call(() =>
            api.DELETE("/api/v1/system/kill-switches/{switch_id}", {
              params: { path: { switch_id: sw.id } },
            }),
          );
      } else {
        await call(() =>
          api.POST("/api/v1/system/kill-switches", {
            body: { scope: "AGENT", target_id: a.agent_code, reason: t("agentsPage.pauseReason") },
            headers: { "Idempotency-Key": idempotencyKey() },
          }),
        );
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["agents"] }),
        qc.invalidateQueries({ queryKey: ["controls"] }),
      ]);
      toast(t(a.paused ? "agentsPage.resumed" : "agentsPage.pausedToast", { name: a.name }));
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <div className="space-y-4" data-testid="page-agents">
      <PageTitle page={page} />
      {agents.isPending && <LoadingSkeleton />}
      {agents.isError && (
        <ProblemDisplay problem={asProblem(agents.error)} onRetry={() => void agents.refetch()} />
      )}
      {agents.data && list.length === 0 && (
        <StateCard
          message={t("pages.agents.empty")}
          actionLabel={t("pages.agents.emptyAction")}
          onAction={() => void agents.refetch()}
        />
      )}
      {list.length > 0 && (
        <div data-testid="state-success" className="space-y-4">
          <div
            className="tf-stagger grid grid-cols-2 gap-3 lg:grid-cols-4"
            role="group"
            aria-label={t("states.summary")}
          >
            <StatTile label={t("agentsPage.statAgents")} value={String(list.length)} icon="spark" />
            <StatTile
              label={t("agentsPage.statEnabled")}
              value={String(list.filter((a) => a.enabled && !a.paused).length)}
              icon="check"
            />
            <StatTile
              label={t("agentsPage.statPaused")}
              value={String(list.filter((a) => a.paused || !a.enabled).length)}
              icon="stop"
            />
            <StatTile
              label={t("agentsPage.statRuns")}
              value={String(list.reduce((n, a) => n + a.stats_24h.runs, 0))}
              icon="clock"
            />
          </div>
          <Card title={t("agentsPage.agents")}>
            <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={t("agentsPage.agents")}>
              <table className="w-full text-sm" data-testid="agents-table">
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th className="py-2 pe-3 font-medium">{t("columns.agent")}</th>
                    <th className="py-2 pe-3 font-medium">{t("columns.status")}</th>
                    <th className="py-2 pe-3 font-medium">{t("agentsPage.chain")}</th>
                    <th className="py-2 pe-3 font-medium">{t("agentsPage.callsPerDay")}</th>
                    <th className="py-2 pe-3 font-medium">{t("agentsPage.runs24h")}</th>
                    <th className="py-2 pe-3 font-medium">
                      <span className="sr-only">{t("agentsPage.actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((a) => (
                    <tr
                      key={a.agent_code}
                      className="border-t border-line align-top"
                      data-testid={`agent-${a.agent_code}`}
                    >
                      <td className="py-2 pe-3">
                        <span className="font-medium">{a.name}</span>
                        <span className="block text-xs text-muted">
                          {a.agent_code} · {t(`agentsPage.kind.${a.kind}`)}
                          {a.is_auditor ? ` · ${t("agentsPage.auditor")}` : ""}
                        </span>
                      </td>
                      <td className="py-2 pe-3">
                        <AgentStatus a={a} />
                      </td>
                      <td className="py-2 pe-3 text-xs">
                        {a.provider_chain.length ? a.provider_chain.map(short).join(" → ") : "—"}
                      </td>
                      <td className="py-2 pe-3 tabular-nums">{a.limits.calls_per_day ?? "—"}</td>
                      <td className="py-2 pe-3 tabular-nums">
                        {a.stats_24h.runs}
                        {a.stats_24h.success_pct !== null ? ` · ${String(a.stats_24h.success_pct)}%` : ""}
                      </td>
                      <td className="py-2">
                        <div className="flex flex-wrap justify-end gap-1">
                          {a.runnable && (
                            <Button variant="primary" onClick={() => setTestRun(a)}>
                              {t("agentsPage.testRun")}
                            </Button>
                          )}
                          <Button onClick={() => setConfig(a)}>{t("agentsPage.configureShort")}</Button>
                          <Button onClick={() => void pause(a)}>
                            {a.paused ? t("actions.resume") : t("actions.pauseAgent")}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <RecentRuns />
        </div>
      )}
      {config && <ConfigDialog agent={config} onClose={() => setConfig(null)} />}
      {testRun && <TestRunDialog agent={testRun} onClose={() => setTestRun(null)} />}
    </div>
  );
}
