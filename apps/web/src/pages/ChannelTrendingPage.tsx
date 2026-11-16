import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { DataTable } from "../components/DataTable";
import { Dialog } from "../components/Dialog";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StatTile } from "../components/StatTile";
import { StateCard } from "../components/StateCard";
import { Tabs } from "../components/Tabs";
import { useToast } from "../components/Toasts";
import { Badge, Button, Card } from "../components/ui";
import { t } from "../i18n";
import { api, call, getPageData, idempotencyKey, ProblemError, type IdeaOut } from "../lib/api/client";
import { useSelectedChannel } from "../lib/channel";
import { GenerateDialog } from "./content/IdeasPage";
import { IdeaStateBadge, pct, SimilarityBadge } from "./content/common";
import { asProblem, LoadingSkeleton, PageTitle, SafetyNote } from "./PageView";
import { getPage, SAMPLE_IDS } from "./registry";

type Tab = "outliers" | "replicate" | "ideas";
const TABS: readonly Tab[] = ["outliers", "replicate", "ideas"];
const KINDS = ["PART_2", "NEW_ANGLE", "UPDATE", "SHORT_FROM_LONG", "LONG_FROM_SHORT", "SERIES"] as const;
type Kind = (typeof KINDS)[number];
const OUTLIER_COLUMNS = ["title", "published", "views", "multiple", "engagedViews", "ctr", "avd"];

/** Outliers need the channel's own analytics (Phase 13); until then the tab shows sample data. */
function Outliers({ channelId }: { channelId: string }) {
  const page = getPage("trending");
  const outliers = useQuery({
    queryKey: ["page", "trending", "outliers", channelId],
    queryFn: () => getPageData(page.api, channelId, SAMPLE_IDS.channel),
  });
  const data = outliers.data;
  return (
    <>
      <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text">
        {t("trending.outliersLater")}
      </p>
      {outliers.isPending && <LoadingSkeleton />}
      {outliers.isError && (
        <ProblemDisplay problem={asProblem(outliers.error)} onRetry={() => void outliers.refetch()} />
      )}
      {data && data.rows.length === 0 && (
        <StateCard
          message={t("pages.trending.empty")}
          actionLabel={t("pages.trending.emptyAction")}
          onAction={() => undefined}
        />
      )}
      {data && data.rows.length > 0 && (
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
                  icon="grow"
                />
              ))}
            </div>
          )}
          <DataTable
            caption={t("trending.outliers")}
            columns={OUTLIER_COLUMNS.map((c) => ({ key: c, label: t(`columns.${c}`) }))}
            rows={data.rows}
          />
        </div>
      )}
    </>
  );
}

function ReplicateDialog({
  onClose,
  channelId,
  sources,
  initialSource,
}: {
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
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/ideas/replicate", {
          params: { path: { channel_id: channelId } },
          body: { youtube_video_id: source, kind, note: note.trim() || null, count: 5 },
          headers: { "Idempotency-Key": idempotencyKey() },
        }),
      );
      toast(t("trending.queued", { title }));
      onClose();
    } catch (e) {
      setError(e instanceof ProblemError ? (e.problem.detail ?? e.problem.title) : t("states.errorTitle"));
    } finally {
      setBusy(false);
    }
  };
  const field = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm";
  return (
    <Dialog open title={t("trending.dialogTitle", { title })} onClose={onClose} testId="replicate-dialog">
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

function IdeaList({ ideas }: { ideas: IdeaOut[] }) {
  return (
    <ul className="space-y-2" data-testid="idea-list">
      {ideas.map((i) => (
        <li key={i.id} className="rounded-lg border border-line p-2 text-sm">
          <p className="font-medium" dir="auto">
            {i.title}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
            <IdeaStateBadge state={i.state} />
            {i.variation_kind && <Badge tone="info">{t(`trending.kinds.${i.variation_kind}`)}</Badge>}
            {i.similarity_to_source !== null && (
              <span className="text-muted">
                {t("trending.toSource", { value: pct(i.similarity_to_source) })}
              </span>
            )}
            <SimilarityBadge idea={i} />
          </p>
        </li>
      ))}
    </ul>
  );
}

/** Page 32 — Channel Trending (US-4.6, ADR-0025): own outliers, replicate own winners, new ideas. */
export function ChannelTrendingPage() {
  const page = getPage("trending");
  const { id } = useParams();
  const { channelId: selected } = useSelectedChannel();
  const channelId = id ?? selected ?? SAMPLE_IDS.channel;
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("outliers");
  const [dialog, setDialog] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const replicate = useQuery({
    queryKey: ["replicate", channelId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/replicate", { params: { path: { channel_id: channelId } } }),
      ),
    enabled: tab !== "outliers",
  });
  const ideas = useQuery({
    queryKey: ["ideas", channelId, "SUGGESTED"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/ideas", {
          params: { path: { channel_id: channelId }, query: { state: "SUGGESTED", limit: 50 } },
        }),
      ),
    enabled: tab === "ideas",
  });
  const winners = replicate.data?.winners ?? [];
  const sources = winners.map((w) => ({ id: w.youtube_video_id, title: w.title }));
  return (
    <div className="space-y-4" data-testid="page-trending">
      <PageTitle page={page}>
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("pages.trending.title")}>
          <Button
            variant="primary"
            onClick={() => {
              setTab("replicate");
              if (sources.length > 0) setDialog(sources[0]?.id ?? null);
            }}
          >
            {t("actions.replicateThis")}
          </Button>
          <Button onClick={() => setGenerating(true)}>{t("trending.ideasAction")}</Button>
        </div>
      </PageTitle>
      <SafetyNote />
      <p className="text-sm text-muted">{t("trending.ownOnly")}</p>
      <Tabs
        tabs={TABS}
        value={tab}
        onChange={setTab}
        label={t("trending.tabs")}
        labelOf={(n) => t(`trending.${n}`)}
      >
        {tab === "outliers" && <Outliers channelId={channelId} />}
        {tab === "replicate" && (
          <>
            {replicate.isPending && <LoadingSkeleton />}
            {replicate.isError && (
              <ProblemDisplay problem={asProblem(replicate.error)} onRetry={() => void replicate.refetch()} />
            )}
            {replicate.data && (
              <div className="grid gap-4 lg:grid-cols-2" data-testid="state-success">
                <Card title={t("trending.winners")}>
                  {winners.length === 0 ? (
                    <p className="text-sm text-muted">{t("trending.noWinners")}</p>
                  ) : (
                    <ul className="space-y-2" data-testid="winners">
                      {winners.map((w) => (
                        <li
                          key={w.youtube_video_id}
                          className="flex flex-wrap items-center justify-between gap-2 text-sm"
                        >
                          <span dir="auto">{w.title}</span>
                          <Button onClick={() => setDialog(w.youtube_video_id)}>
                            {t("actions.replicateThis")}
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
                <Card title={t("trending.variations")}>
                  {replicate.data.variations.length === 0 ? (
                    <p className="text-sm text-muted">{t("trending.replicateEmpty")}</p>
                  ) : (
                    <IdeaList ideas={replicate.data.variations} />
                  )}
                </Card>
              </div>
            )}
          </>
        )}
        {tab === "ideas" && (
          <>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => setGenerating(true)}>
                {t("trending.ideasAction")}
              </Button>
              <Link className="self-center text-sm text-accent underline" to={`/channels/${channelId}/ideas`}>
                {t("pages.ideas.title")}
              </Link>
            </div>
            {ideas.isPending && <LoadingSkeleton />}
            {ideas.isError && (
              <ProblemDisplay problem={asProblem(ideas.error)} onRetry={() => void ideas.refetch()} />
            )}
            {ideas.data && ideas.data.items.length === 0 && (
              <StateCard
                message={t("trending.ideasEmpty")}
                actionLabel={t("trending.ideasAction")}
                onAction={() => setGenerating(true)}
              />
            )}
            {ideas.data && ideas.data.items.length > 0 && (
              <div data-testid="state-success">
                <IdeaList ideas={ideas.data.items} />
              </div>
            )}
          </>
        )}
      </Tabs>
      {dialog !== null && (
        <ReplicateDialog
          onClose={() => {
            setDialog(null);
            void qc.invalidateQueries({ queryKey: ["replicate", channelId] });
          }}
          channelId={channelId}
          sources={sources}
          initialSource={dialog}
        />
      )}
      {generating && (
        <GenerateDialog channelId={channelId} open={generating} onClose={() => setGenerating(false)} />
      )}
    </div>
  );
}
