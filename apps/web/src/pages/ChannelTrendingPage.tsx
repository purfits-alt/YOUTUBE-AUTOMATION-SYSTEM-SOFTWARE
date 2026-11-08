import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { DataTable } from "../components/DataTable";
import { Dialog } from "../components/Dialog";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StatTile } from "../components/StatTile";
import { StateCard } from "../components/StateCard";
import { useToast } from "../components/Toasts";
import { Button } from "../components/ui";
import { t } from "../i18n";
import { call, getPageData, idempotencyKey, ProblemError, stubApi, type PageData } from "../lib/api/client";
import { asProblem, LoadingSkeleton, PageTitle, SafetyNote } from "./PageView";
import { getPage, SAMPLE_IDS } from "./registry";

type Tab = "outliers" | "replicate" | "ideas";
const TABS: readonly Tab[] = ["outliers", "replicate", "ideas"];
const KINDS = ["PART_2", "NEW_ANGLE", "UPDATE", "SHORT_FROM_LONG", "LONG_FROM_SHORT", "SERIES"] as const;
type Kind = (typeof KINDS)[number];

const COLUMNS: Record<Tab, readonly string[]> = {
  outliers: ["title", "published", "views", "multiple", "engagedViews", "ctr", "avd"],
  replicate: ["title", "variation", "angle", "similarity", "state"],
  ideas: ["title", "format", "reason", "similarity", "state"],
};

function TabData({
  tab,
  query,
  emptyMessage,
  emptyAction,
  onEmptyAction,
}: {
  tab: Tab;
  query: {
    data: PageData | undefined;
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
  };
  emptyMessage: string;
  emptyAction: string;
  onEmptyAction: () => void;
}) {
  const data = query.data;
  const empty = data !== undefined && data.rows.length === 0;
  return (
    <>
      {query.isPending && <LoadingSkeleton />}
      {query.isError && (
        <ProblemDisplay problem={asProblem(query.error)} onRetry={() => void query.refetch()} />
      )}
      {empty && <StateCard message={emptyMessage} actionLabel={emptyAction} onAction={onEmptyAction} />}
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
                  icon={tab === "ideas" ? "spark" : tab === "replicate" ? "film" : "grow"}
                />
              ))}
            </div>
          )}
          <DataTable
            caption={t(`trending.${tab}`)}
            columns={COLUMNS[tab].map((c) => ({ key: c, label: t(`columns.${c}`) }))}
            rows={data.rows}
          />
        </div>
      )}
    </>
  );
}

function ReplicateDialog({
  open,
  onClose,
  channelId,
  sources,
  initialSource,
}: {
  open: boolean;
  onClose: () => void;
  channelId: string;
  sources: { id: string; title: string }[];
  initialSource: string | undefined;
}) {
  const toast = useToast();
  const [source, setSource] = useState(initialSource ?? sources[0]?.id ?? "");
  const [kind, setKind] = useState<Kind>("PART_2");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const title = sources.find((s) => s.id === source)?.title ?? "";
  const submit = async () => {
    setBusy(true);
    setError(null);
    const key = idempotencyKey();
    try {
      const r = await call(() =>
        stubApi.POST("/channels/{id}/ideas/replicate", {
          params: { path: { id: channelId } },
          body: { youtube_video_id: source, kind, ...(note.trim() ? { note: note.trim() } : {}) },
          headers: { "Idempotency-Key": key },
        }),
      );
      toast(t("trending.created", { title: r.idea_title }));
      onClose();
    } catch (e) {
      if (e instanceof ProblemError && e.problem.code === "TOO_SIMILAR") setError(t("trending.tooSimilar"));
      else
        setError(e instanceof ProblemError ? (e.problem.detail ?? e.problem.title) : t("states.errorTitle"));
    } finally {
      setBusy(false);
    }
  };
  const field = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm";
  return (
    <Dialog
      open={open}
      title={t("trending.dialogTitle", { title })}
      onClose={onClose}
      testId="replicate-dialog"
    >
      <p className="text-sm text-muted">{t("trending.guard")}</p>
      <label htmlFor="rep-source" className="mt-3 block text-sm font-medium">
        {t("trending.source")}
      </label>
      <select id="rep-source" className={field} value={source} onChange={(e) => setSource(e.target.value)}>
        {sources.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title}
          </option>
        ))}
      </select>
      <label htmlFor="rep-kind" className="mt-3 block text-sm font-medium">
        {t("trending.kind")}
      </label>
      <select id="rep-kind" className={field} value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {t(`trending.kinds.${k}`)}
          </option>
        ))}
      </select>
      <label htmlFor="rep-note" className="mt-3 block text-sm font-medium">
        {t("trending.note")}
      </label>
      <textarea
        id="rep-note"
        rows={2}
        maxLength={500}
        className={field}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {error && (
        <p role="alert" className="mt-3 rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text">
          {error}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={onClose}>{t("confirm.cancel")}</Button>
        <Button variant="primary" disabled={busy || !source} onClick={() => void submit()}>
          {t("trending.create")}
        </Button>
      </div>
    </Dialog>
  );
}

/** Page 32 — Channel Trending (US-4.6, ADR-0025): own outliers, replicate own winners, new ideas. */
export function ChannelTrendingPage() {
  const page = getPage("trending");
  const { id } = useParams();
  const channelId = id ?? SAMPLE_IDS.channel;
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("outliers");
  const [dialog, setDialog] = useState(false);
  const base = useId();
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    outliers: null,
    replicate: null,
    ideas: null,
  });

  const outliers = useQuery({
    queryKey: ["page", "trending", "outliers", channelId],
    queryFn: () => getPageData(page.api, channelId, SAMPLE_IDS.channel),
  });
  const replicate = useQuery({
    queryKey: ["page", "trending", "replicate", channelId],
    queryFn: () =>
      call(() => stubApi.GET("/channels/{id}/replicate", { params: { path: { id: channelId } } })),
    enabled: tab === "replicate",
  });
  const ideas = useQuery({
    queryKey: ["page", "trending", "ideas", channelId],
    queryFn: () => getPageData("/channels/{id}/ideas", channelId, SAMPLE_IDS.channel),
    enabled: tab === "ideas",
  });

  const sources = (outliers.data?.rows ?? []).map((r) => ({ id: r.id, title: String(r.title ?? r.id) }));
  const queued = (action: string) => toast(t("toast.actionQueued", { action }));

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    const next = TABS[(index + delta + TABS.length) % TABS.length] ?? "outliers";
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="space-y-4" data-testid="page-trending">
      <PageTitle page={page}>
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("pages.trending.title")}>
          <Button variant="primary" onClick={() => setDialog(true)} disabled={sources.length === 0}>
            {t("actions.replicateThis")}
          </Button>
          <Button onClick={() => queued(t("actions.refreshAnalytics"))}>
            {t("actions.refreshAnalytics")}
          </Button>
        </div>
      </PageTitle>
      <SafetyNote />
      <p className="text-sm text-muted">{t("trending.ownOnly")}</p>

      <div
        role="tablist"
        aria-label={t("trending.tabs")}
        className="flex gap-1 rounded-xl border border-line bg-surface p-1"
      >
        {TABS.map((name, i) => (
          <button
            key={name}
            ref={(el) => {
              tabRefs.current[name] = el;
            }}
            id={`${base}-tab-${name}`}
            type="button"
            role="tab"
            aria-selected={tab === name}
            aria-controls={`${base}-panel-${name}`}
            tabIndex={tab === name ? 0 : -1}
            onClick={() => setTab(name)}
            onKeyDown={(e) => onKey(e, i)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              tab === name ? "bg-accent text-accent-fg shadow-glow" : "text-fg hover:bg-surface-2"
            }`}
          >
            {t(`trending.${name}`)}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`${base}-panel-${tab}`}
        aria-labelledby={`${base}-tab-${tab}`}
        className="space-y-4"
      >
        {tab === "outliers" && (
          <TabData
            tab="outliers"
            query={outliers}
            emptyMessage={t("pages.trending.empty")}
            emptyAction={t("pages.trending.emptyAction")}
            onEmptyAction={() => queued(t("actions.refreshAnalytics"))}
          />
        )}
        {tab === "replicate" && (
          <TabData
            tab="replicate"
            query={replicate}
            emptyMessage={t("trending.replicateEmpty")}
            emptyAction={t("trending.outliers")}
            onEmptyAction={() => setTab("outliers")}
          />
        )}
        {tab === "ideas" && (
          <>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => queued(t("trending.ideasAction"))}>
                {t("trending.ideasAction")}
              </Button>
              <Button onClick={() => void navigate(`/channels/${channelId}/ideas`)}>
                {t("pages.ideas.title")}
              </Button>
            </div>
            <TabData
              tab="ideas"
              query={ideas}
              emptyMessage={t("trending.ideasEmpty")}
              emptyAction={t("trending.ideasAction")}
              onEmptyAction={() => queued(t("trending.ideasAction"))}
            />
          </>
        )}
      </div>

      {dialog && (
        <ReplicateDialog
          open={dialog}
          onClose={() => setDialog(false)}
          channelId={channelId}
          sources={sources}
          initialSource={sources[0]?.id}
        />
      )}
    </div>
  );
}
