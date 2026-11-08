import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useParams } from "react-router";
import { DataTable } from "../components/DataTable";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { ProjectHeader } from "../components/ProjectHeader";
import { StatTile } from "../components/StatTile";
import { StateCard } from "../components/StateCard";
import { useToast } from "../components/Toasts";
import { Icon, type IconName } from "../components/icons";
import { Button, Skeleton } from "../components/ui";
import { t } from "../i18n";
import { getPageData, ProblemError, type Problem } from "../lib/api/client";
import { SAMPLE_IDS } from "./registry";
import type { PageDef } from "./types";

const GROUP_ICON: Record<PageDef["group"], IconName> = {
  home: "home",
  discover: "discover",
  channels: "channels",
  create: "create",
  publish: "publish",
  grow: "grow",
  library: "library",
  control: "control",
};

/** Page hero: group eyebrow, title, purpose, optional actions on the right. */
export function PageTitle({ page, children }: { page: PageDef; children?: ReactNode }) {
  return (
    <div className="tf-hero tf-card tf-rise flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-line px-5 py-5 sm:px-6">
      <div className="min-w-0">
        <p className="flex items-center gap-1.5 text-xs font-semibold tracking-[0.14em] text-accent uppercase">
          <Icon name={GROUP_ICON[page.group]} className="size-3.5" />
          {t(`groups.${page.group}`)} · {page.num}
        </p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">{t(`pages.${page.id}.title`)}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">{t(`pages.${page.id}.purpose`)}</p>
      </div>
      {children}
    </div>
  );
}

export function SafetyNote() {
  return (
    <p data-testid="safety-note" className="tf-rise rounded-lg bg-info-soft px-3 py-2 text-sm text-info-text">
      <span aria-hidden="true">i </span>
      {t("safety")}
    </p>
  );
}

export function asProblem(error: unknown): Problem {
  if (error instanceof ProblemError) return error.problem;
  return { title: t("states.errorTitle"), status: 0, code: "CLIENT", detail: String(error) };
}

export function LoadingSkeleton() {
  return (
    <div data-testid="state-loading" aria-busy="true" className="space-y-3">
      <span className="sr-only">{t("states.loading")}</span>
      <div className="flex gap-3">
        <Skeleton className="h-20 w-40" />
        <Skeleton className="h-20 w-40" />
      </div>
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

/** Generic page frame used by pages 2–31: title, actions, data in one of the four standard states. */
export function PageView({ page }: { page: PageDef }) {
  const { id, candidateId } = useParams();
  const toast = useToast();
  const routeId = id ?? candidateId;
  const query = useQuery({
    queryKey: ["page", page.id, routeId],
    // Pages without an id in the URL (e.g. Analytics) use the selected channel.
    queryFn: () => getPageData(page.api, routeId, SAMPLE_IDS.channel),
  });
  const title = t(`pages.${page.id}.title`);
  const act = (key: string) => toast(t("toast.actionQueued", { action: t(`actions.${key}`) }));
  const data = query.data;
  const empty = data !== undefined && data.rows.length === 0;

  return (
    <div className="space-y-4" data-testid={`page-${page.id}`}>
      <PageTitle page={page}>
        <div className="flex flex-wrap gap-2" role="group" aria-label={title}>
          {page.actions.map((a, i) => (
            <Button key={a} variant={i === 0 ? "primary" : "secondary"} onClick={() => act(a)}>
              {t(`actions.${a}`)}
            </Button>
          ))}
        </div>
      </PageTitle>
      {page.safety && <SafetyNote />}
      {data?.project && <ProjectHeader project={data.project} />}
      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {empty && (
        <StateCard
          message={t(`pages.${page.id}.empty`)}
          actionLabel={t(`pages.${page.id}.emptyAction`)}
          onAction={() => act(page.actions[0] ?? "refresh")}
        />
      )}
      {data && !empty && (
        <div data-testid="state-success" className="space-y-4">
          {data.stats.length > 0 && (
            <div
              className="tf-stagger flex gap-3 overflow-x-auto pb-1"
              role="group"
              aria-label={t("states.summary")}
              tabIndex={0}
            >
              {data.stats.map((s) => (
                <StatTile
                  key={s.key}
                  label={s.label}
                  value={s.value}
                  hint={s.hint}
                  delta={s.delta}
                  deltaGood={s.delta_good}
                  trend={s.trend}
                  icon={GROUP_ICON[page.group]}
                />
              ))}
            </div>
          )}
          <DataTable
            caption={title}
            columns={page.columns.map((c) => ({ key: c, label: t(`columns.${c}`) }))}
            rows={data.rows}
          />
        </div>
      )}
    </div>
  );
}
