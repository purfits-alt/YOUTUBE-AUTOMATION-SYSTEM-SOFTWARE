import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { JobProgress } from "../components/JobProgress";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StateCard } from "../components/StateCard";
import { Badge, Button, Card, type Tone } from "../components/ui";
import { t } from "../i18n";
import { api, call } from "../lib/api/client";
import type { components } from "../lib/api/schema";
import { useSelectedChannel } from "../lib/channel";
import { asProblem, LoadingSkeleton, PageTitle } from "./PageView";
import { getPage } from "./registry";

type PipelineOut = components["schemas"]["PipelineOut"];
type Item = PipelineOut["projects"][number];
type Station = PipelineOut["stations"][number];

const ACTIVITY_TONE: Record<Item["activity"], Tone> = {
  QUEUED: "neutral",
  WORKING: "info",
  STALLED: "warn",
  STOPPED: "danger",
  WAITING: "warn",
  YOUR_TURN: "ok",
  NOT_BUILT: "neutral",
  PAUSED: "neutral",
  BLOCKED: "danger",
  DONE: "ok",
};

function who(s: Station): string {
  return s.who === "OWNER" ? t("pipeline.you") : t("pipeline.tubeforge");
}

type BoardItem = NonNullable<NonNullable<Station["board"]>["inbox"]>[number];

function BoardList({ items, showPct = false }: { items: BoardItem[]; showPct?: boolean }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5">
      {items.slice(0, 3).map((x) => (
        <li key={x.id} className="truncate">
          <Link className="text-accent underline" to={`/projects/${x.id}/script`} dir="auto">
            {x.title}
          </Link>
          {showPct && x.pct != null && <span className="text-muted tabular-nums"> · {x.pct}%</span>}
        </li>
      ))}
      {items.length > 3 && (
        <li className="text-muted">{t("pipeline.board.more", { n: items.length - 3 })}</li>
      )}
    </ul>
  );
}

function Box({
  title,
  count,
  tone,
  testId,
  children,
}: {
  title: string;
  count: number;
  tone: string;
  testId: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={`min-w-0 rounded-lg border px-2 py-1.5 ${tone}`} data-testid={testId}>
      <p className="flex items-baseline justify-between gap-1">
        <span className="truncate font-medium">{title}</span>
        <span className="text-base font-bold tabular-nums">{count}</span>
      </p>
      {children}
    </div>
  );
}

/** State board (owner request 2026-11-18): one card per station with its inbox (and where it came
 * from), work in progress, completed work and what it forwarded to the next station. */
function StateBoard({ stations }: { stations: Station[] }) {
  return (
    <section aria-label={t("pipeline.board.title")} data-testid="stations">
      <h2 className="mb-2 text-sm font-semibold">{t("pipeline.board.title")}</h2>
      <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {stations.map((s, i) => {
          const b = s.board && {
            ...s.board,
            inbox: s.board.inbox ?? [],
            in_progress: s.board.in_progress ?? [],
            forwarded: s.board.forwarded ?? [],
            attention: s.board.attention ?? 0,
            complete: s.board.complete ?? 0,
          };
          return (
            <li
              key={s.key}
              data-testid={`station-${s.key}`}
              className={`tf-card rounded-xl border p-3 text-xs ${
                !s.ready
                  ? "border-dashed border-line bg-surface text-muted"
                  : s.who === "OWNER"
                    ? "border-accent bg-surface"
                    : "border-line bg-surface"
              }`}
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-1">
                <p className="text-sm font-semibold">
                  <span className="text-muted tabular-nums">{i + 1}.</span> {s.label}
                </p>
                <Badge tone={!s.ready ? "neutral" : s.who === "OWNER" ? "ok" : "info"}>
                  {s.ready ? who(s) : t("pipeline.arrives", { phase: s.phase })}
                </Badge>
              </div>
              {b && (
                <div className="grid grid-cols-2 gap-1.5">
                  <Box
                    title={t("pipeline.board.inbox")}
                    count={b.inbox.length}
                    tone="border-line bg-surface-2"
                    testId="box-inbox"
                  >
                    <p className="text-muted">{t("pipeline.board.from", { name: b.received_from ?? "—" })}</p>
                    <BoardList items={b.inbox} />
                  </Box>
                  <Box
                    title={t("pipeline.board.inProgress")}
                    count={b.in_progress.length}
                    tone={b.attention > 0 ? "border-warn-text bg-warn-soft" : "border-line bg-info-soft"}
                    testId="box-progress"
                  >
                    {b.attention > 0 && (
                      <p className="font-medium text-warn-text">
                        {t("pipeline.board.attention", { n: b.attention })}
                      </p>
                    )}
                    <BoardList items={b.in_progress} showPct />
                  </Box>
                  <Box
                    title={t("pipeline.board.complete")}
                    count={b.complete}
                    tone="border-line bg-ok-soft"
                    testId="box-complete"
                  />
                  <Box
                    title={t("pipeline.board.forwarded")}
                    count={b.forwarded.length}
                    tone="border-line bg-surface-2"
                    testId="box-forwarded"
                  >
                    <p className="text-muted">
                      {b.forwards_to ? t("pipeline.board.to", { name: b.forwards_to }) : t("pipeline.end")}
                    </p>
                    <BoardList items={b.forwarded} />
                  </Box>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function NextStation({ next }: { next: Item["next"] }) {
  if (!next) return <>{t("pipeline.end")}</>;
  if (!next.ready) return <>{t("pipeline.nextLater", { label: next.label, phase: next.phase })}</>;
  return (
    <>
      {next.who === "OWNER"
        ? t("pipeline.nextYou", { label: next.label })
        : t("pipeline.nextAuto", { label: next.label })}
    </>
  );
}

/** One video on the line: current station with live %, the next station, and a dot per station. */
function ProjectRow({ item, stations }: { item: Item; stations: Station[] }) {
  const current = stations.find((s) => s.key === item.station);
  const explain = ["YOUR_TURN", "STALLED", "STOPPED", "NOT_BUILT", "PAUSED"].includes(item.activity)
    ? t(`pipeline.explain.${item.activity}`, { phase: item.next?.phase ?? "" })
    : null;
  return (
    <li className="space-y-2 py-3" data-testid={`pipeline-${item.id}`} data-activity={item.activity}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link className="font-medium text-accent underline" to={item.link} dir="auto">
            {item.title}
          </Link>
          <p className="text-xs text-muted">
            {item.channel_name} · {t(`content.format.${item.format}`)}
          </p>
        </div>
        <Badge tone={ACTIVITY_TONE[item.activity]}>{t(`pipeline.activity.${item.activity}`)}</Badge>
      </div>
      <ol
        aria-label={t("pipeline.steps", { title: item.title })}
        className="flex flex-wrap items-center gap-1"
        data-testid="steps"
      >
        {item.steps.map((step) => {
          const s = stations.find((x) => x.key === step.key);
          return (
            <li
              key={step.key}
              aria-current={step.status === "current" ? "step" : undefined}
              title={`${s?.label ?? step.key} — ${t(`pipeline.step.${step.status}`)}`}
              className={`h-2 rounded-full ${
                step.status === "done"
                  ? "w-5 bg-ok-text"
                  : step.status === "current"
                    ? "w-8 bg-accent"
                    : step.status === "next"
                      ? "w-5 border border-accent"
                      : "w-5 bg-surface-2"
              }`}
            >
              <span className="sr-only">
                {s?.label}: {t(`pipeline.step.${step.status}`)}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted uppercase">{t("pipeline.now")}</p>
          {item.progress ? (
            <JobProgress job={item.progress} />
          ) : (
            <p>
              {current?.label} {current && <span className="text-muted">({who(current)})</span>}
            </p>
          )}
        </div>
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted uppercase">{t("pipeline.next")}</p>
          <p data-testid="next">
            <NextStation next={item.next} />
          </p>
        </div>
      </div>
      {explain && <p className="text-xs text-muted">{explain}</p>}
    </li>
  );
}

/** Page 33 — Pipeline (ADR-0031): the whole production line, live. */
export function PipelinePage() {
  const navigate = useNavigate();
  const { channelId } = useSelectedChannel();
  const query = useQuery({
    queryKey: ["pipeline"],
    queryFn: () => call(() => api.GET("/api/v1/pipeline")),
    refetchInterval: (q) => (q.state.data?.refresh_s ?? 20) * 1000,
  });
  const data = query.data;
  return (
    <div className="space-y-4" data-testid="page-pipeline">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle page={getPage("pipeline")} />
        <Button onClick={() => void query.refetch()}>{t("actions.refresh")}</Button>
      </div>
      <p className="text-sm text-muted">
        {t("pipeline.hint")} {data && <span>{t("pipeline.live", { s: data.refresh_s })}</span>}
      </p>
      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {data && (
        <div className="space-y-4" data-testid={data.projects.length > 0 ? "state-success" : undefined}>
          <StateBoard stations={data.stations} />
          {data.projects.length === 0 ? (
            <StateCard
              message={t("pages.pipeline.empty")}
              actionLabel={t("pages.pipeline.emptyAction")}
              onAction={() => void navigate(channelId ? `/channels/${channelId}/ideas` : "/channels")}
            />
          ) : (
            <Card title={t("pipeline.videos")}>
              <ul className="divide-y divide-line" data-testid="pipeline-projects">
                {data.projects.map((item) => (
                  <ProjectRow key={item.id} item={item} stations={data.stations} />
                ))}
              </ul>
            </Card>
          )}
          {data.jobs.length > 0 && (
            <Card title={t("pipeline.otherWork")}>
              <p className="mb-2 text-xs text-muted">{t("pipeline.otherHint")}</p>
              <ul className="space-y-3" data-testid="pipeline-jobs">
                {data.jobs.map((job) => (
                  <li key={job.id} className="flex flex-wrap items-end justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <JobProgress job={job} />
                    </div>
                    {job.link && (
                      <Link className="text-sm text-accent underline" to={job.link}>
                        {t("pipeline.open")}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
