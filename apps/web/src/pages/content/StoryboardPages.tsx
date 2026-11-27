import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { JobProgress } from "../../components/JobProgress";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { hasKey, t } from "../../i18n";
import {
  api,
  call,
  idempotencyKey,
  type SceneOut,
  type StoryboardOut,
  type TemplateOut,
} from "../../lib/api/client";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";

const STYLES = [
  "kinetic_text",
  "motion_graphics",
  "chart",
  "photo",
  "owner_footage",
  "screen_recording",
] as const;
type Style = (typeof STYLES)[number];
type Retry = "retry-storyboard" | "retry-visuals";

function useStoryboard(id: string) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["storyboard", id],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/storyboard", { params: { path: { project_id: id } } }),
      ),
    // Live while the storyboard or visuals job works (ADR-0031).
    refetchInterval: (q) =>
      q.state.data?.job && ["QUEUED", "RUNNING"].includes(q.state.data.job.status) ? 3000 : false,
  });
  const toast = useToast();
  const retry = async (cmd: Retry) => {
    try {
      await call(() =>
        api.POST("/api/v1/projects/{project_id}/commands/{cmd}", {
          params: { path: { project_id: id, cmd } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: {},
        }),
      );
      toast(t(`storyboardPage.done.${cmd}`));
      void qc.invalidateQueries({ queryKey: ["storyboard", id] });
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return { query, retry };
}

function Summary({ data, children }: { data: StoryboardOut; children?: React.ReactNode }) {
  const off = Math.abs(data.total_duration_s - data.target_duration_s) / Math.max(data.target_duration_s, 1);
  return (
    <section
      aria-label={t("storyboardPage.summary")}
      className="tf-card flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-4 text-sm"
      data-testid="storyboard-summary"
    >
      <span className="font-semibold" dir="auto">
        {data.working_title}
      </span>
      <Badge tone="neutral">
        {hasKey(`content.projectState.${data.project_state}`)
          ? t(`content.projectState.${data.project_state}`)
          : data.project_state}
      </Badge>
      {data.version !== null && (
        <span className="text-muted">
          {t("storyboardPage.version", {
            n: data.version,
            who: t(`storyboardPage.author.${data.author_type ?? "AGENT"}`),
          })}
        </span>
      )}
      <span>{t("storyboardPage.scenes", { n: data.scenes.length })}</span>
      <Badge tone={off <= 0.1 ? "ok" : "warn"}>
        {t("storyboardPage.duration", {
          s: Math.round(data.total_duration_s),
          target: data.target_duration_s,
        })}
      </Badge>
      <span className="ms-auto flex flex-wrap gap-2">{children}</span>
    </section>
  );
}

function SceneBadges({ scene }: { scene: SceneOut }) {
  return (
    <>
      {scene.is_hook && <Badge tone="info">{t("storyboardPage.hook")}</Badge>}
      {scene.pattern_interrupt && <Badge tone="warn">{t("storyboardPage.interrupt")}</Badge>}
      <span className="text-xs text-muted">
        {t("storyboardPage.seconds", { s: scene.duration_s.toFixed(1) })}
      </span>
    </>
  );
}

function Waiting({
  data,
  page,
  onRetry,
}: {
  data: StoryboardOut;
  page: "storyboard" | "visuals";
  onRetry: () => void;
}) {
  const working = data.job && ["QUEUED", "RUNNING"].includes(data.job.status);
  const canRetry =
    !working &&
    ((page === "storyboard" && data.project_state === "STORYBOARDING") ||
      (page === "visuals" && data.project_state === "ASSET_GENERATION"));
  return (
    <StateCard
      message={
        working
          ? t(`storyboardPage.working.${page}`)
          : data.version === null &&
              ["IDEA", "RESEARCHING", "RESEARCH_REVIEW", "SCRIPTING", "SCRIPT_REVIEW"].includes(
                data.project_state,
              )
            ? t("storyboardPage.afterScript")
            : t(`pages.${page}.empty`)
      }
      actionLabel={canRetry ? t(`storyboardPage.retry.${page}`) : undefined}
      onAction={canRetry ? onRetry : undefined}
    />
  );
}

interface Draft {
  visual_instruction: string;
  on_screen_text: string;
  style: Style;
}

function draftOf(s: SceneOut): Draft {
  return {
    visual_instruction: s.visual_instruction,
    on_screen_text: s.on_screen_text ?? "",
    style: (STYLES as readonly string[]).includes(s.style ?? "") ? (s.style as Style) : "kinetic_text",
  };
}

/** Page 12 — Storyboard Studio (Phase 8 step B): the locked script cut into scenes. Narration is the
 * script word for word; the owner changes what each scene shows, and each save is a new version. */
export function StoryboardPage() {
  const { id = "" } = useParams();
  const toast = useToast();
  const qc = useQueryClient();
  const { query, retry } = useStoryboard(id);
  const data = query.data;
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState(false);
  const loadedVersion = useRef<number | null>(null);
  useEffect(() => {
    if (data && data.version !== loadedVersion.current) {
      loadedVersion.current = data.version;
      setDrafts(Object.fromEntries(data.scenes.map((s) => [s.id, draftOf(s)])));
    }
  }, [data]);
  const dirty =
    data?.scenes.some((s) => {
      const d = drafts[s.id];
      const o = draftOf(s);
      return (
        d &&
        (d.visual_instruction !== o.visual_instruction ||
          d.on_screen_text !== o.on_screen_text ||
          d.style !== o.style)
      );
    }) ?? false;
  const save = async () => {
    if (!data || data.version === null) return;
    setSaving(true);
    try {
      await call(() =>
        api.PUT("/api/v1/projects/{project_id}/storyboard", {
          params: { path: { project_id: id } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: {
            based_on_version: data.version ?? 0,
            scenes: data.scenes.map((s) => {
              const d = drafts[s.id] ?? draftOf(s);
              return {
                id: s.id,
                visual_instruction: d.visual_instruction.trim() || s.visual_instruction,
                on_screen_text: d.on_screen_text.trim() || null,
                style: d.style,
              };
            }),
          },
        }),
      );
      toast(t("storyboardPage.saved"));
      void qc.invalidateQueries({ queryKey: ["storyboard", id] });
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setSaving(false);
    }
  };
  const set = (sceneId: string, patch: Partial<Draft>) =>
    setDrafts((all) => ({ ...all, [sceneId]: { ...(all[sceneId] as Draft), ...patch } }));
  return (
    <div className="space-y-4" data-testid="page-storyboard">
      <PageTitle page={getPage("storyboard")} />
      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {data && (
        <>
          <Summary data={data}>
            {data.project_state === "STORYBOARDING" && data.version !== null && (
              <Button onClick={() => void retry("retry-storyboard")}>
                {t("storyboardPage.retry.storyboard")}
              </Button>
            )}
            {data.version !== null && (
              <Link className="text-accent underline" to={`/projects/${id}/visuals`}>
                {t("storyboardPage.toVisuals")}
              </Link>
            )}
            <Link className="text-accent underline" to={`/projects/${id}/script`}>
              {t("storyboardPage.toScript")}
            </Link>
          </Summary>
          {data.job && <JobProgress job={data.job} />}
          {data.version === null ? (
            <Waiting data={data} page="storyboard" onRetry={() => void retry("retry-storyboard")} />
          ) : (
            <>
              <p className="text-sm text-muted">
                {data.editable ? t("storyboardPage.hint") : t("storyboardPage.locked")}
              </p>
              <ol className="space-y-3" data-testid="state-success">
                {data.scenes.map((s) => {
                  const d = drafts[s.id] ?? draftOf(s);
                  return (
                    <li key={s.id} data-testid={`scene-${String(s.position)}`}>
                      <Card
                        title={t("storyboardPage.scene", { n: s.position })}
                        actions={<SceneBadges scene={s} />}
                      >
                        <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
                          <div>
                            <p className="text-xs font-semibold text-muted uppercase">
                              {t("storyboardPage.narration")}
                            </p>
                            <p className="mt-1 text-sm whitespace-pre-line" dir="auto">
                              {s.narration}
                            </p>
                          </div>
                          <div className="space-y-2">
                            <label className="block text-sm">
                              <span className="font-medium">{t("storyboardPage.visual")}</span>
                              <textarea
                                className={`${inputCls} mt-1 min-h-16`}
                                value={d.visual_instruction}
                                maxLength={1000}
                                disabled={!data.editable}
                                onChange={(e) => set(s.id, { visual_instruction: e.target.value })}
                              />
                            </label>
                            <label className="block text-sm">
                              <span className="font-medium">{t("storyboardPage.onScreen")}</span>
                              <input
                                className={`${inputCls} mt-1`}
                                value={d.on_screen_text}
                                maxLength={120}
                                disabled={!data.editable}
                                onChange={(e) => set(s.id, { on_screen_text: e.target.value })}
                              />
                            </label>
                            <label className="block text-sm">
                              <span className="font-medium">{t("storyboardPage.style")}</span>
                              <select
                                className={`${inputCls} mt-1`}
                                value={d.style}
                                disabled={!data.editable}
                                onChange={(e) => set(s.id, { style: e.target.value as Style })}
                              >
                                {STYLES.map((st) => (
                                  <option key={st} value={st}>
                                    {t(`storyboardPage.styles.${st}`)}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                        </div>
                      </Card>
                    </li>
                  );
                })}
              </ol>
              {data.editable && (
                <div className="flex justify-end">
                  <Button variant="primary" disabled={!dirty || saving} onClick={() => void save()}>
                    {t("storyboardPage.save")}
                  </Button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------- Visual Studio
interface FieldSchema {
  type?: string;
  items?: { type?: string };
  maxLength?: number;
  maxItems?: number;
  default?: unknown;
  anyOf?: FieldSchema[];
}

function kindOf(f: FieldSchema): "text" | "lines" | "numbers" | "int" {
  if (f.type === "array") return f.items?.type === "number" ? "numbers" : "lines";
  if (f.type === "integer") return "int";
  return "text";
}

function toInput(kind: ReturnType<typeof kindOf>, value: unknown): string {
  if (Array.isArray(value)) return kind === "numbers" ? value.join(", ") : value.join("\n");
  return value === undefined || value === null ? "" : String(value);
}

function fromInput(kind: ReturnType<typeof kindOf>, raw: string): unknown {
  if (kind === "lines")
    return raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
  if (kind === "numbers")
    return raw
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean)
      .map(Number);
  if (kind === "int") return raw === "" ? 0 : Math.round(Number(raw));
  return raw;
}

function SceneVisual({
  projectId,
  scene,
  templates,
  editable,
  onQueued,
}: {
  projectId: string;
  scene: SceneOut;
  templates: TemplateOut[];
  editable: boolean;
  onQueued: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [templateId, setTemplateId] = useState(scene.template_id ?? "kinetic_title");
  const [values, setValues] = useState<Record<string, string>>({});
  const template = templates.find((x) => x.id === templateId);
  const fields = Object.entries((template?.fields ?? {}) as Record<string, FieldSchema>);
  const start = (id: string) => {
    setTemplateId(id);
    const chosen = templates.find((x) => x.id === id);
    const same = id === scene.template_id;
    setValues(
      Object.fromEntries(
        Object.entries((chosen?.fields ?? {}) as Record<string, FieldSchema>).map(([name, f]) => [
          name,
          toInput(kindOf(f), same ? scene.template_params[name] : (f.default ?? "")),
        ]),
      ),
    );
  };
  const send = async () => {
    const params = Object.fromEntries(
      fields.map(([name, f]) => [name, fromInput(kindOf(f), values[name] ?? "")]),
    );
    try {
      await call(() =>
        api.PUT("/api/v1/projects/{project_id}/scenes/{scene_id}/visual", {
          params: { path: { project_id: projectId, scene_id: scene.id } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { template_id: templateId, params },
        }),
      );
      toast(t("visualsPage.queued", { n: scene.position }));
      setOpen(false);
      onQueued();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <Card title={t("storyboardPage.scene", { n: scene.position })} actions={<SceneBadges scene={scene} />}>
      <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        {scene.visual_url ? (
          <img
            src={scene.visual_url}
            alt={t("visualsPage.alt", { n: scene.position })}
            className="w-full rounded-lg border border-line object-contain"
            loading="lazy"
          />
        ) : (
          <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-line text-sm text-muted">
            {t("visualsPage.noPicture")}
          </div>
        )}
        <div className="space-y-2 text-sm">
          <p>
            <span className="font-medium">{scene.template_label ?? t("visualsPage.none")}</span>
            {scene.treatment && (
              <span className="text-muted"> · {t(`visualsPage.treatment.${scene.treatment}`)}</span>
            )}
          </p>
          <p className="text-muted" dir="auto">
            {scene.narration}
          </p>
          {scene.note && <p className="text-xs">{t("visualsPage.note", { note: scene.note })}</p>}
          {scene.chart_claim_ids.length > 0 && (
            <p className="text-xs">{t("visualsPage.claims", { ids: scene.chart_claim_ids.join(", ") })}</p>
          )}
          {scene.stock_search_terms.length > 0 && (
            <p className="text-xs text-muted">
              {t("visualsPage.stock", { terms: scene.stock_search_terms.join(" · ") })}
            </p>
          )}
          {scene.visual_url && <Badge tone="ok">{t("visualsPage.rights")}</Badge>}
          {editable && !open && (
            <div>
              <Button
                onClick={() => {
                  start(scene.template_id ?? "kinetic_title");
                  setOpen(true);
                }}
              >
                {t("visualsPage.change")}
              </Button>
            </div>
          )}
          {open && (
            <form
              className="space-y-2 rounded-lg border border-line p-3"
              aria-label={t("visualsPage.changeLabel", { n: scene.position })}
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
            >
              <label className="block">
                <span className="font-medium">{t("visualsPage.template")}</span>
                <select
                  className={`${inputCls} mt-1`}
                  value={templateId}
                  onChange={(e) => start(e.target.value)}
                >
                  {templates.map((x) => (
                    <option key={x.id} value={x.id} disabled={x.needs_media}>
                      {x.needs_media ? t("visualsPage.later", { label: x.label }) : x.label}
                    </option>
                  ))}
                </select>
              </label>
              {template && <p className="text-xs text-muted">{template.use_for}</p>}
              {fields.map(([name, f]) => {
                const kind = kindOf(f);
                const label = hasKey(`visualsPage.field.${name}`) ? t(`visualsPage.field.${name}`) : name;
                return (
                  <label key={name} className="block">
                    <span className="font-medium">{label}</span>
                    {kind === "lines" ? (
                      <textarea
                        className={`${inputCls} mt-1 min-h-16`}
                        value={values[name] ?? ""}
                        onChange={(e) => setValues({ ...values, [name]: e.target.value })}
                      />
                    ) : (
                      <input
                        className={`${inputCls} mt-1`}
                        inputMode={kind === "text" ? undefined : "decimal"}
                        value={values[name] ?? ""}
                        maxLength={f.maxLength}
                        onChange={(e) => setValues({ ...values, [name]: e.target.value })}
                      />
                    )}
                    {kind === "lines" && (
                      <span className="text-xs text-muted">{t("visualsPage.onePerLine")}</span>
                    )}
                    {kind === "numbers" && (
                      <span className="text-xs text-muted">{t("visualsPage.commaNumbers")}</span>
                    )}
                  </label>
                );
              })}
              <div className="flex gap-2">
                <Button type="submit" variant="primary">
                  {t("visualsPage.draw")}
                </Button>
                <Button onClick={() => setOpen(false)}>{t("confirm.cancel")}</Button>
              </div>
            </form>
          )}
        </div>
      </div>
    </Card>
  );
}

/** Page 14 — Visual Studio (Phase 8 step B): one drawn picture per scene, each with a rights record;
 * the owner can pick another template or change its text. */
export function VisualsPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { query, retry } = useStoryboard(id);
  const data = query.data;
  const ready = data ? data.scenes.filter((s) => s.visual_url).length : 0;
  return (
    <div className="space-y-4" data-testid="page-visuals">
      <PageTitle page={getPage("visuals")} />
      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {data && (
        <>
          <Summary data={data}>
            {data.version !== null && (
              <Badge tone={ready === data.scenes.length ? "ok" : "warn"}>
                {t("visualsPage.ready", { n: ready, total: data.scenes.length })}
              </Badge>
            )}
            {data.project_state === "ASSET_GENERATION" && ready > 0 && (
              <Button onClick={() => void retry("retry-visuals")}>{t("storyboardPage.retry.visuals")}</Button>
            )}
            <Link className="text-accent underline" to={`/projects/${id}/storyboard`}>
              {t("visualsPage.toStoryboard")}
            </Link>
          </Summary>
          {data.job && <JobProgress job={data.job} />}
          {ready === 0 ? (
            <Waiting data={data} page="visuals" onRetry={() => void retry("retry-visuals")} />
          ) : (
            <>
              <p className="text-sm text-muted">{t("visualsPage.hint")}</p>
              <ol className="space-y-3" data-testid="state-success">
                {data.scenes.map((s) => (
                  <li key={s.id} data-testid={`visual-${String(s.position)}`}>
                    <SceneVisual
                      projectId={id}
                      scene={s}
                      templates={data.templates}
                      editable={data.editable}
                      onQueued={() => void qc.invalidateQueries({ queryKey: ["storyboard", id] })}
                    />
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
    </div>
  );
}
