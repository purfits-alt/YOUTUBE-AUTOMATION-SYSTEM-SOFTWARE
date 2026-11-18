import { t } from "../i18n";
import type { components } from "../lib/api/schema";
import { Badge, type Tone } from "./ui";

export type JobProgressOut = components["schemas"]["JobProgressOut"];

const STATUS_TONE: Record<JobProgressOut["status"], Tone> = {
  QUEUED: "neutral",
  RUNNING: "info",
  DONE: "ok",
  FAILED: "danger",
  WAITING: "warn",
  STALLED: "warn",
};

export function timeLeft(seconds: number): string {
  return seconds < 90
    ? t("pipeline.seconds", { n: Math.max(5, Math.round(seconds / 5) * 5) })
    : t("pipeline.minutes", { n: Math.round(seconds / 60) });
}

/** A live job: label, % bar, stage in plain words, time left, and why it stopped or waits (ADR-0031). */
export function JobProgress({ job, compact = false }: { job: JobProgressOut; compact?: boolean }) {
  const moving = job.status === "RUNNING" || job.status === "QUEUED";
  const bar =
    job.status === "FAILED"
      ? "bg-danger"
      : job.status === "DONE"
        ? "bg-ok-text"
        : moving
          ? "bg-accent"
          : "bg-warn-text";
  return (
    <div className="space-y-1" data-testid="job-progress" data-status={job.status}>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{job.label}</span>
        <Badge tone={STATUS_TONE[job.status]}>{t(`pipeline.status.${job.status}`)}</Badge>
        <span className="tabular-nums" data-testid="job-pct">
          {job.pct}%
        </span>
        {job.eta_s != null && job.status === "RUNNING" && (
          <span className="text-muted">· {t("pipeline.left", { t: timeLeft(job.eta_s) })}</span>
        )}
      </p>
      <div
        role="progressbar"
        aria-label={t("pipeline.progress", { label: job.label, pct: job.pct })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={job.pct}
        aria-valuetext={`${String(job.pct)}% — ${job.stage}`}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className={`h-full ${bar} transition-[width] duration-700 ${moving ? "tf-progress-live" : ""}`}
          style={{ width: `${String(Math.max(job.status === "QUEUED" ? 0 : 3, job.pct))}%` }}
        />
      </div>
      <p className="text-xs text-muted" aria-live="polite">
        {job.stage}
      </p>
      {!compact && job.message && job.status !== "DONE" && (
        <p className="text-xs" dir="auto" data-testid="job-message">
          {job.message}
        </p>
      )}
      {!compact && job.hint && (
        <p className="text-xs text-warn-text" data-testid="job-hint">
          {job.hint}
        </p>
      )}
    </div>
  );
}
