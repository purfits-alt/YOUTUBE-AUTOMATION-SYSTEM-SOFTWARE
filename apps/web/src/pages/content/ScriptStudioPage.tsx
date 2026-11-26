import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router";
import { Dialog } from "../../components/Dialog";
import { JobProgress } from "../../components/JobProgress";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import {
  api,
  call,
  idempotencyKey,
  type ClaimOut,
  type ProjectOut,
  type ValueAddIn,
  type VersionOut,
} from "../../lib/api/client";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import { useChannelName, VERDICT_TONE } from "./common";

const STEPS = [
  "IDEA",
  "RESEARCHING",
  "RESEARCH_REVIEW",
  "SCRIPTING",
  "SCRIPT_REVIEW",
  "STORYBOARDING",
] as const;
type Command =
  | "start"
  | "retry-research"
  | "retry-script"
  | "approve-research"
  | "request-research-changes"
  | "approve-script"
  | "request-script-changes"
  | "retry"
  | "pause"
  | "resume"
  | "cancel";

interface ScriptBody {
  promise_delivery?: { promise_statement?: string; delivered_at_s?: number; text?: string };
  hook?: { text?: string; est_s?: number; technique?: string[] };
  sections?: { heading: string; text: string; fact_refs: string[]; beat?: string }[];
  re_hooks?: { at_pct: number; technique: string; text: string }[];
  open_loops?: { id: string; opened_in_section: number; closed_in_section: number; text: string }[];
  payoff?: string;
  cta?: string;
  owner_slots?: { section_index: number; prompt: string }[];
  [key: string]: unknown;
}

function ProjectPanel({
  project,
  channelName,
  onCommand,
}: {
  project: ProjectOut;
  channelName: string;
  onCommand: (cmd: Command, note?: string) => void;
}) {
  const current = STEPS.indexOf(project.state as (typeof STEPS)[number]);
  const promise = project.packaging_promise as {
    thumbnail_text_idea?: string;
    promise_statement?: string;
  } | null;
  return (
    <section
      aria-label={t("project.header")}
      data-testid="project-header"
      className="tf-card tf-rise rounded-xl border border-line bg-surface p-5"
    >
      <p className="text-lg font-semibold" dir="auto">
        {project.working_title}
      </p>
      <p className="mt-0.5 text-sm text-muted">
        {t("project.channel")}: {channelName} · {t("project.format")}: {t(`content.format.${project.format}`)}{" "}
        · {t("scriptPage.target", { s: project.target_duration_s })}
      </p>
      {promise?.promise_statement && (
        <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-sm" data-testid="packaging-promise">
          <span className="font-medium">{t("ideasPage.promise")}:</span> “{promise.thumbnail_text_idea}” —{" "}
          {promise.promise_statement}
        </p>
      )}
      <ol aria-label={t("project.stepper")} className="mt-3 flex flex-wrap gap-1.5 text-xs">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i === current ? "step" : undefined}
            className={`rounded-full border px-2 py-0.5 ${
              i === current
                ? "border-accent bg-accent font-semibold text-accent-fg"
                : i < current
                  ? "border-line bg-surface-2"
                  : "border-line text-muted"
            }`}
          >
            {i < current && <span aria-hidden="true">✓ </span>}
            {t(`content.projectState.${s}`)}
          </li>
        ))}
        {current < 0 && (
          <li className="rounded-full border border-warn px-2 py-0.5 font-semibold">
            {t(`content.projectState.${project.state}`)}
          </li>
        )}
      </ol>
      {project.progress && (
        <div className="mt-3 max-w-xl" data-testid="project-progress">
          <JobProgress job={project.progress} />
        </div>
      )}
      {(project.checks ?? []).length > 0 && (
        <div className="mt-3" data-testid="checks">
          <p className="text-sm font-medium">{t("project.guards")}</p>
          <ul className="mt-1 space-y-1 text-sm">
            {(project.checks ?? []).map((c) => (
              <li key={c.code} className="flex items-start gap-2">
                <Badge tone={c.ok ? "ok" : "warn"}>{t(`scriptPage.check.${c.code}`)}</Badge>
                {!c.ok && <span className="text-muted">{c.message}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2" data-testid="commands">
        {(project.allowed_commands ?? []).map((cmd) =>
          cmd === "retry-research" || cmd === "retry-script" ? (
            <RetryBox key={cmd} cmd={cmd} onRetry={(note) => onCommand(cmd, note)} />
          ) : (
            <Button
              key={cmd}
              variant={
                cmd.startsWith("approve") || cmd === "start"
                  ? "primary"
                  : cmd === "cancel"
                    ? "ghost"
                    : "secondary"
              }
              onClick={() => onCommand(cmd as Command)}
            >
              {t(`scriptPage.cmd.${cmd}`)}
            </Button>
          ),
        )}
      </div>
    </section>
  );
}

/** A job found too little, was refused or stopped: run it again — research with optional extra
 * search words, the script with an optional instruction for the new draft. */
function RetryBox({
  cmd,
  onRetry,
}: {
  cmd: "retry-research" | "retry-script";
  onRetry: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const research = cmd === "retry-research";
  return (
    <div className="flex w-full flex-wrap items-end gap-2" data-testid={cmd}>
      <div className="min-w-0 flex-1">
        <label htmlFor={`${cmd}-note`} className="block text-sm font-medium">
          {t(research ? "scriptPage.extraWords" : "scriptPage.scriptNote")}
        </label>
        <input
          id={`${cmd}-note`}
          className={inputCls}
          value={note}
          placeholder={t(research ? "scriptPage.extraWordsHint" : "scriptPage.scriptNoteHint")}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <Button variant="primary" onClick={() => onRetry(note.trim())}>
        {t(`scriptPage.cmd.${cmd}`)}
      </Button>
    </div>
  );
}

function OverrideDialog({
  claim,
  onClose,
  onDone,
}: {
  claim: ClaimOut;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const submit = async () => {
    try {
      await call(() =>
        api.POST("/api/v1/claims/{claim_id}/override", {
          params: { path: { claim_id: claim.id } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { reason: reason.trim() },
        }),
      );
      toast(t("scriptPage.overridden"));
      onDone();
      onClose();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <Dialog open title={t("scriptPage.overrideTitle")} onClose={onClose} testId="override-dialog">
      <p className="text-sm" dir="auto">
        {claim.claim_text}
      </p>
      <p className="mt-1 text-xs text-muted">{claim.explanation}</p>
      <label htmlFor="override-reason" className="mt-3 block text-sm font-medium">
        {t("scriptPage.overrideReason")}
      </label>
      <textarea
        id="override-reason"
        rows={3}
        className={inputCls}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onClose}>{t("actions.cancel")}</Button>
        <Button variant="primary" disabled={reason.trim().length < 20} onClick={() => void submit()}>
          {t("scriptPage.override")}
        </Button>
      </div>
    </Dialog>
  );
}

function Claims({ claims, title, onChanged }: { claims: ClaimOut[]; title: string; onChanged: () => void }) {
  const [overriding, setOverriding] = useState<ClaimOut | null>(null);
  if (claims.length === 0) return null;
  return (
    <Card title={title}>
      <ul className="space-y-2" data-testid="claims">
        {claims.map((c) => (
          <li key={c.id} className="rounded-lg border border-line p-2 text-sm">
            <p dir="auto">{c.claim_text}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
              <Badge tone={c.owner_override_reason ? "info" : VERDICT_TONE[c.verdict]}>
                {t(`scriptPage.verdict.${c.verdict}`)}
              </Badge>
              {c.owner_override_reason && <Badge tone="info">{t("scriptPage.accepted")}</Badge>}
              <span className="text-muted">{c.explanation}</span>
            </p>
            {c.sources.length > 0 && (
              <ul className="mt-1 text-xs">
                {c.sources.map((s) => (
                  <li key={s.id}>
                    <a
                      className="text-accent underline"
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {s.title ?? s.url}
                    </a>
                  </li>
                ))}
              </ul>
            )}
            {(c.verdict === "CONTRADICTED" || c.verdict === "UNSUPPORTED") && !c.owner_override_reason && (
              <Button className="mt-2" onClick={() => setOverriding(c)}>
                {t("scriptPage.override")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {overriding && (
        <OverrideDialog claim={overriding} onClose={() => setOverriding(null)} onDone={onChanged} />
      )}
    </Card>
  );
}

/** Hook timer and re-hook markers (A11 craft rules): what the owner checks at a glance. */
function Timing({ version, format }: { version: VersionOut; format: ProjectOut["format"] }) {
  const body = version.body as ScriptBody;
  const [low, high] = format === "SHORT" ? [0, 3] : [10, 15];
  const ok = version.hook_s >= low && version.hook_s <= high;
  const total = Math.max(version.est_duration_s, 1);
  return (
    <div className="space-y-2" data-testid="timing">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{t("scriptPage.hookTimer")}</span>
        <Badge tone={ok ? "ok" : "warn"}>
          {t("scriptPage.hookSeconds", { s: version.hook_s.toFixed(1), low, high })}
        </Badge>
        <span className="text-muted">
          {t("scriptPage.length", {
            m: Math.floor(version.est_duration_s / 60),
            s: String(version.est_duration_s % 60).padStart(2, "0"),
            words: version.word_count,
          })}
        </span>
      </p>
      <div
        className="relative h-6 rounded-full bg-surface-2"
        role="img"
        aria-label={t("scriptPage.rehookBar", { n: (body.re_hooks ?? []).length })}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-l-full bg-accent/40"
          style={{ width: `${String(Math.min(100, ((body.hook?.est_s ?? version.hook_s) / total) * 100))}%` }}
        />
        {(body.re_hooks ?? []).map((r) => (
          <span
            key={`${String(r.at_pct)}-${r.technique}`}
            title={r.text}
            className="absolute top-0 h-6 w-1 rounded bg-warn"
            style={{ left: `${String(r.at_pct)}%` }}
          />
        ))}
      </div>
      <p className="text-xs text-muted">{t("scriptPage.rehookHint")}</p>
    </div>
  );
}

function Editor({
  projectId,
  version,
  onSaved,
}: {
  projectId: string;
  version: VersionOut;
  onSaved: (n: number) => void;
}) {
  const toast = useToast();
  const [body, setBody] = useState<ScriptBody>(version.body as ScriptBody);
  useEffect(() => setBody(version.body as ScriptBody), [version]);
  const set = (patch: Partial<ScriptBody>) => setBody((b) => ({ ...b, ...patch }));
  const setSection = (i: number, text: string) =>
    set({ sections: (body.sections ?? []).map((s, j) => (j === i ? { ...s, text } : s)) });
  const save = async () => {
    try {
      const out = await call(() =>
        api.POST("/api/v1/projects/{project_id}/script/versions", {
          params: { path: { project_id: projectId } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { body: body as Record<string, unknown>, based_on_version: version.version },
        }),
      );
      toast(t("scriptPage.saved", { v: out.version }));
      onSaved(out.version);
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const area = (id: string, label: string, value: string, onChange: (v: string) => void, rows = 3) => (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <textarea
        id={id}
        rows={rows}
        className={inputCls}
        dir="auto"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
  return (
    <div className="space-y-3" data-testid="editor">
      {area(
        "hook",
        t("scriptPage.hook"),
        body.hook?.text ?? "",
        (v) => set({ hook: { ...body.hook, text: v } }),
        2,
      )}
      {area(
        "promise",
        t("scriptPage.promiseText"),
        body.promise_delivery?.text ?? "",
        (v) => set({ promise_delivery: { ...body.promise_delivery, text: v } }),
        2,
      )}
      {(body.sections ?? []).map((s, i) => (
        <div key={`${String(i)}-${s.heading}`}>
          {area(`section-${String(i)}`, `${String(i + 1)}. ${s.heading}`, s.text, (v) => setSection(i, v), 6)}
          {s.text.includes("[[OWNER:") && (
            <p className="mt-1 text-xs text-warn-text">{t("scriptPage.ownerSlot")}</p>
          )}
        </div>
      ))}
      {area("payoff", t("scriptPage.payoff"), body.payoff ?? "", (v) => set({ payoff: v }), 2)}
      {area("cta", t("scriptPage.cta"), body.cta ?? "", (v) => set({ cta: v }), 2)}
      <Button variant="primary" onClick={() => void save()}>
        {t("scriptPage.saveVersion")}
      </Button>
    </div>
  );
}

function ValueAdd({ projectId }: { projectId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const current = useQuery({
    queryKey: ["value-add", projectId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/value-add", { params: { path: { project_id: projectId } } }),
      ),
  });
  const [form, setForm] = useState<ValueAddIn>({
    owner_voice: "NONE",
    owner_footage: false,
    owner_photos: false,
  });
  useEffect(() => {
    if (current.data) {
      const v = current.data;
      setForm({
        own_experience: v.own_experience ?? null,
        own_opinion: v.own_opinion ?? null,
        own_data: v.own_data ?? null,
        own_examples: v.own_examples ?? null,
        owner_voice: v.owner_voice,
        owner_footage: v.owner_footage,
        owner_photos: v.owner_photos,
      });
    }
  }, [current.data]);
  const save = async () => {
    try {
      await call(() =>
        api.PUT("/api/v1/projects/{project_id}/value-add", {
          params: { path: { project_id: projectId } },
          body: form,
        }),
      );
      toast(t("scriptPage.valueSaved"));
      void qc.invalidateQueries({ queryKey: ["value-add", projectId] });
      void qc.invalidateQueries({ queryKey: ["project", projectId] });
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const fields = ["own_experience", "own_opinion", "own_data", "own_examples"] as const;
  return (
    <Card title={t("scriptPage.valueAdd")}>
      <p className="mb-2 text-sm text-muted">{t("scriptPage.valueHint")}</p>
      <p className="mb-2 text-sm" data-testid="value-score">
        {t("scriptPage.valueScore", { score: Number(current.data?.score ?? 0).toFixed(0) })}
      </p>
      <div className="space-y-2">
        {fields.map((f) => (
          <div key={f}>
            <label htmlFor={`va-${f}`} className="block text-sm font-medium">
              {t(`scriptPage.va.${f}`)}
            </label>
            <textarea
              id={`va-${f}`}
              rows={2}
              className={inputCls}
              dir="auto"
              value={form[f] ?? ""}
              onChange={(e) => setForm({ ...form, [f]: e.target.value })}
            />
          </div>
        ))}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.owner_footage ?? false}
            onChange={(e) => setForm({ ...form, owner_footage: e.target.checked })}
          />
          {t("scriptPage.va.owner_footage")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.owner_photos ?? false}
            onChange={(e) => setForm({ ...form, owner_photos: e.target.checked })}
          />
          {t("scriptPage.va.owner_photos")}
        </label>
        <Button onClick={() => void save()}>{t("scriptPage.saveValue")}</Button>
      </div>
    </Card>
  );
}

function Regenerate({ projectId, onQueued }: { projectId: string; onQueued: () => void }) {
  const toast = useToast();
  const [instruction, setInstruction] = useState("");
  const submit = async () => {
    try {
      await call(() =>
        api.POST("/api/v1/projects/{project_id}/script/regenerate", {
          params: { path: { project_id: projectId } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { instruction: instruction.trim() },
        }),
      );
      toast(t("scriptPage.regenerateQueued"));
      setInstruction("");
      onQueued();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="min-w-0 flex-1">
        <label htmlFor="regen" className="block text-sm font-medium">
          {t("scriptPage.instruction")}
        </label>
        <input
          id="regen"
          className={inputCls}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
      </div>
      <Button disabled={instruction.trim().length < 5} onClick={() => void submit()}>
        {t("scriptPage.regenerate")}
      </Button>
    </div>
  );
}

function Diff({ projectId, latest }: { projectId: string; latest: number }) {
  const [a, setA] = useState(Math.max(1, latest - 1));
  const diff = useQuery({
    queryKey: ["diff", projectId, a, latest],
    enabled: latest > 1,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/script/diff", {
          params: { path: { project_id: projectId }, query: { a, b: latest } },
        }),
      ),
  });
  if (latest < 2) return null;
  return (
    <Card title={t("scriptPage.diff", { b: latest })}>
      <label className="text-sm">
        {t("scriptPage.compareWith")}{" "}
        <select
          className="rounded border border-line bg-bg px-2 py-1"
          value={a}
          onChange={(e) => setA(Number(e.target.value))}
        >
          {Array.from({ length: latest - 1 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              v{n}
            </option>
          ))}
        </select>
      </label>
      <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-surface-2 p-2 text-xs" data-testid="diff">
        {(diff.data?.lines ?? []).map((line, i) => (
          <span
            key={i}
            className={
              line.startsWith("+")
                ? "block text-ok-text"
                : line.startsWith("-")
                  ? "block text-danger-text"
                  : "block"
            }
          >
            {line}
          </span>
        ))}
      </pre>
    </Card>
  );
}

/** Page 11 — Script Studio (Phase 7): research brief, claims, script versions, craft checks, value-add. */
export function ScriptStudioPage() {
  const page = getPage("script");
  const { id = "" } = useParams();
  const toast = useToast();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })),
    // Live while a job works on this project (ADR-0031); the page follows it to the next station.
    refetchInterval: (q) =>
      q.state.data?.progress && ["QUEUED", "RUNNING"].includes(q.state.data.progress.status) ? 3000 : false,
  });
  const versions = useQuery({
    queryKey: ["versions", id],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/script/versions", { params: { path: { project_id: id } } }),
      ),
  });
  const latest = versions.data?.[0]?.version ?? 0;
  const shown = selected ?? latest;
  const version = useQuery({
    queryKey: ["version", id, shown],
    enabled: shown > 0,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/script/versions/{number}", {
          params: { path: { project_id: id, number: shown } },
        }),
      ),
  });
  const briefs = useQuery({
    queryKey: ["briefs", id],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/research", { params: { path: { project_id: id } } })),
  });
  const claims = useQuery({
    queryKey: ["claims", id],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/claims", { params: { path: { project_id: id } } })),
  });
  const channelName = useChannelName(project.data?.channel_id);
  const refresh = () => {
    for (const key of ["project", "versions", "version", "briefs", "claims"])
      void qc.invalidateQueries({ queryKey: [key, id] });
  };
  // When the job finishes or the project moves on, load the new brief, draft and claims by themselves.
  const step = `${project.data?.state ?? ""}:${project.data?.progress?.status ?? ""}`;
  const lastStep = useRef(step);
  useEffect(() => {
    if (lastStep.current !== step && lastStep.current !== ":") {
      for (const key of ["versions", "version", "briefs", "claims"])
        void qc.invalidateQueries({ queryKey: [key, id] });
    }
    lastStep.current = step;
  }, [step, id, qc]);
  const command = async (cmd: Command, note?: string) => {
    try {
      await call(() =>
        api.POST("/api/v1/projects/{project_id}/commands/{cmd}", {
          params: { path: { project_id: id, cmd } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: note ? { note } : {},
        }),
      );
      toast(t(`scriptPage.done.${cmd}`));
      refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const brief = briefs.data?.[0];
  const briefContent = (brief?.content ?? {}) as { summary?: string; open_questions?: string[] };
  const allClaims = claims.data ?? [];
  const briefClaims = allClaims.filter(
    (c) => c.subject_type === "RESEARCH_BRIEF" && c.subject_id === brief?.id,
  );
  const scriptClaims = allClaims.filter(
    (c) => c.subject_type === "SCRIPT_VERSION" && c.subject_id === version.data?.id,
  );
  const p = project.data;
  return (
    <div className="space-y-4" data-testid="page-script">
      <PageTitle page={page} />
      {project.isError && (
        <ProblemDisplay problem={asProblem(project.error)} onRetry={() => void project.refetch()} />
      )}
      {p && (
        <ProjectPanel project={p} channelName={channelName} onCommand={(c, note) => void command(c, note)} />
      )}
      {brief && (
        <Card
          title={t("scriptPage.brief", {
            v: brief.version,
            status: t(`scriptPage.briefStatus.${brief.status}`),
          })}
        >
          <p className="text-sm" dir="auto">
            {briefContent.summary}
          </p>
          {(briefContent.open_questions ?? []).length > 0 && (
            <>
              <p className="mt-2 text-sm font-medium">{t("scriptPage.openQuestions")}</p>
              <ul className="list-disc pl-5 text-sm">
                {(briefContent.open_questions ?? []).map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}
      <Claims claims={briefClaims} title={t("scriptPage.briefClaims")} onChanged={refresh} />
      {versions.isPending && <LoadingSkeleton />}
      {versions.isError && (
        <ProblemDisplay problem={asProblem(versions.error)} onRetry={() => void versions.refetch()} />
      )}
      {versions.data && versions.data.length === 0 && (
        <StateCard
          message={t("pages.script.empty")}
          actionLabel={t("pages.script.emptyAction")}
          onAction={() => toast(t("scriptPage.waitResearch"))}
        />
      )}
      {versions.data && versions.data.length > 0 && (
        <div data-testid="state-success" className="grid gap-4 xl:grid-cols-[1fr_22rem]">
          <div className="space-y-4">
            <Card
              title={t("scriptPage.script")}
              actions={
                <select
                  aria-label={t("scriptPage.version")}
                  className="rounded border border-line bg-bg px-2 py-1 text-sm"
                  value={shown}
                  onChange={(e) => setSelected(Number(e.target.value))}
                >
                  {versions.data.map((v) => (
                    <option key={v.id} value={v.version}>
                      v{v.version} · {t(`scriptPage.author.${v.author_type}`)}
                      {v.locked ? ` · ${t("scriptPage.locked")}` : ""}
                    </option>
                  ))}
                </select>
              }
            >
              {version.data && p && (
                <div className="space-y-4">
                  <Timing version={version.data} format={p.format} />
                  <p className="flex flex-wrap gap-2 text-xs">
                    <Badge tone={version.data.fact_check === "PENDING" ? "warn" : "ok"}>
                      {t(`scriptPage.factCheck.${version.data.fact_check}`)}
                    </Badge>
                    {version.data.locked && <Badge tone="info">{t("scriptPage.locked")}</Badge>}
                  </p>
                  {version.data.findings.length > 0 ? (
                    <ul className="space-y-1 text-sm" data-testid="findings">
                      {version.data.findings.map((f) => (
                        <li key={`${f.code}-${f.message}`} className="flex items-start gap-2">
                          <Badge tone={f.severity === "ERROR" ? "danger" : "warn"}>{f.code}</Badge>
                          <span>{f.message}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-ok-text" data-testid="findings">
                      {t("scriptPage.allChecksPass")}
                    </p>
                  )}
                  {(p.state === "SCRIPT_REVIEW" || p.state === "SCRIPTING") && shown === latest ? (
                    <Editor
                      projectId={id}
                      version={version.data}
                      onSaved={(n) => {
                        setSelected(n);
                        refresh();
                      }}
                    />
                  ) : (
                    <pre
                      className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm"
                      dir="auto"
                    >
                      {version.data.plain_text}
                    </pre>
                  )}
                  {p.state === "SCRIPT_REVIEW" && <Regenerate projectId={id} onQueued={refresh} />}
                </div>
              )}
            </Card>
            <Diff projectId={id} latest={latest} />
          </div>
          <div className="space-y-4">
            <ValueAdd projectId={id} />
            <Claims claims={scriptClaims} title={t("scriptPage.scriptClaims")} onChanged={refresh} />
          </div>
        </div>
      )}
    </div>
  );
}
