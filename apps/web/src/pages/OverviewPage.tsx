import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { AreaChart, Ring } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { Icon, type IconName } from "../components/icons";
import { Lottie } from "../components/Lottie";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StatTile } from "../components/StatTile";
import { StateCard } from "../components/StateCard";
import { Badge, Button, Card, toneFor } from "../components/ui";
import { t } from "../i18n";
import { api, call } from "../lib/api/client";
import { useShell } from "../lib/useShell";
import { asProblem, LoadingSkeleton } from "./PageView";
import { getPage } from "./registry";

const KPI_ICONS: Record<string, IconName> = {
  channels: "channels",
  projects: "film",
  approvals: "check",
  quota: "gauge",
  usage: "spark",
};

/** Page 1 — Overview Dashboard (FRONTEND_SPECIFICATION §1). */
export function OverviewPage() {
  const page = getPage("overview");
  const navigate = useNavigate();
  const shell = useShell();
  const query = useQuery({
    queryKey: ["overview"],
    queryFn: () => call(() => api.GET("/dashboard/overview")),
  });
  const data = query.data;
  const empty = data !== undefined && data.kpis.length === 0;
  const pipelineMax = Math.max(1, ...(data?.pipeline.map((p) => p.count) ?? [1]));

  return (
    <div className="space-y-5" data-testid="page-overview">
      <div className="tf-hero tf-card tf-rise relative flex flex-wrap items-center justify-between gap-4 overflow-hidden rounded-2xl border border-line px-5 py-5 sm:px-6">
        <div className="flex min-w-0 items-center gap-4">
          <Lottie name="studio-orb" className="size-20 shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-[0.14em] text-accent uppercase">
              {t("overview.studioLive")}
            </p>
            <h1 className="mt-0.5 text-2xl font-bold tracking-tight sm:text-3xl">
              {t(`pages.${page.id}.title`)}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-muted">{t("overview.studioDetail")}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => void navigate("/approvals")} variant="primary">
            <Icon name="check" />
            {t("actions.openApproval")}
          </Button>
          <Button onClick={() => void query.refetch()}>{t("actions.refresh")}</Button>
        </div>
      </div>

      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {empty && (
        <StateCard
          message={t("pages.overview.empty")}
          actionLabel={t("pages.overview.emptyAction")}
          onAction={() => void navigate("/discovery")}
        />
      )}
      {data && !empty && (
        <div data-testid="state-success" className="space-y-5">
          <div
            className="tf-stagger flex gap-3 overflow-x-auto pb-1"
            aria-label={t("overview.kpis")}
            role="group"
            // Scrollable on narrow screens: keyboard users must be able to focus and scroll it.
            tabIndex={0}
          >
            {data.kpis.map((k) => (
              <StatTile
                key={k.key}
                label={k.label}
                value={k.value}
                hint={k.hint}
                delta={k.delta}
                deltaGood={k.delta_good}
                trend={k.trend}
                icon={KPI_ICONS[k.key] ?? "spark"}
              />
            ))}
          </div>

          <div className="grid gap-5 lg:grid-cols-12">
            <Card title={t("overview.views")} className="lg:col-span-8">
              <AreaChart data={data.views_14d} label={t("overview.viewsLabel")} />
            </Card>
            <Card title={t("topbar.quota")} className="lg:col-span-4">
              <div className="space-y-5">
                <Ring
                  value={shell.data?.quota.youtube_default_pct ?? 0}
                  label={t("overview.quotaRing")}
                  sublabel={t("overview.quotaSub")}
                />
                <Ring
                  value={shell.data?.quota.free_tier_peak_pct ?? 0}
                  label={t("overview.usageRing")}
                  sublabel={t("overview.usageSub")}
                />
              </div>
            </Card>

            <Card title={t("overview.funnel")} className="lg:col-span-7">
              <ul className="space-y-2.5">
                {data.pipeline.map((p) => (
                  <li key={p.state} className="grid grid-cols-[7rem_1fr_2.5rem] items-center gap-3 text-sm">
                    <span className="text-xs font-semibold tracking-wide text-muted">{p.state}</span>
                    <span
                      className="relative h-2.5 overflow-hidden rounded-full bg-surface-2"
                      aria-hidden="true"
                    >
                      <span
                        className="tf-grow absolute inset-y-0 start-0 rounded-full bg-gradient-to-r from-[#ff5f6d] to-accent"
                        style={{ width: `${String(Math.max(4, (p.count / pipelineMax) * 100))}%` }}
                      />
                    </span>
                    <span className="text-end font-semibold tabular-nums">{p.count}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card
              title={t("overview.approvals")}
              className="lg:col-span-5"
              actions={
                <Link to="/approvals" className="text-sm font-medium text-accent underline">
                  {t("actions.openApproval")}
                </Link>
              }
            >
              <ul className="divide-y divide-line">
                {data.approvals.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <span className="flex min-w-0 items-center gap-2.5">
                      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
                        <Icon name="check" />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-medium" dir="auto">
                          {String(a.subject)}
                        </span>
                        <span className="text-xs text-muted">{String(a.type)}</span>
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1 text-xs text-muted">
                      <Icon name="clock" className="size-3.5" />
                      {String(a.age)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title={t("overview.alerts")} className="lg:col-span-6">
              <ul className="space-y-3">
                {data.alerts.map((a) => (
                  <li key={a.id} className="flex items-start gap-2.5 text-sm">
                    <Badge tone={toneFor(String(a.severity))}>{String(a.severity)}</Badge>
                    <span>{String(a.message)}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title={t("overview.schedule")} className="lg:col-span-6">
              <ul className="divide-y divide-line">
                {data.schedule.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <span className="flex min-w-0 items-center gap-2.5">
                      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2">
                        <Icon name="clock" />
                      </span>
                      <span className="min-w-0" dir="auto">
                        <span className="block truncate font-medium">{String(s.title)}</span>
                        <span className="text-xs text-muted">{String(s.channel)}</span>
                      </span>
                    </span>
                    <span className="shrink-0 text-xs font-medium tabular-nums">{String(s.date)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card
            title={t("overview.activity")}
            actions={
              <Link to="/security" className="text-sm font-medium text-accent underline">
                {t("overview.openAudit")}
              </Link>
            }
          >
            <DataTable
              caption={t("overview.activity")}
              columns={page.columns.map((c) => ({ key: c, label: t(`columns.${c}`) }))}
              rows={data.activity}
            />
          </Card>
        </div>
      )}
    </div>
  );
}
