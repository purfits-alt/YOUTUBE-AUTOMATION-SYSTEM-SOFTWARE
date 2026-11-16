import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Dialog } from "../../components/Dialog";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type IdeaOut } from "../../lib/api/client";
import { useSelectedChannel } from "../../lib/channel";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import {
  FORMATS,
  IdeaStateBadge,
  NoBlueprintHint,
  SimilarityBadge,
  useChannelName,
  type Format,
} from "./common";

const FILTERS = [
  "ALL",
  "SUGGESTED",
  "SHORTLISTED",
  "SCHEDULED",
  "APPROVED",
  "IN_PRODUCTION",
  "DISCARDED",
] as const;
type Filter = (typeof FILTERS)[number];

export function GenerateDialog({
  channelId,
  open,
  onClose,
}: {
  channelId: string;
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const [count, setCount] = useState(10);
  const [format, setFormat] = useState<Format | "">("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/ideas/generate", {
          params: { path: { channel_id: channelId } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { count, format: format || null },
        }),
      );
      toast(t("ideasPage.generateQueued"));
      onClose();
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} title={t("ideasPage.generateTitle")} onClose={onClose} testId="generate-dialog">
      <div className="space-y-3">
        <div>
          <label htmlFor="gen-count" className="block text-sm font-medium">
            {t("ideasPage.count")}
          </label>
          <input
            id="gen-count"
            type="number"
            min={1}
            max={20}
            className={inputCls}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
          />
        </div>
        <div>
          <label htmlFor="gen-format" className="block text-sm font-medium">
            {t("ideasPage.format")}
          </label>
          <select
            id="gen-format"
            className={inputCls}
            value={format}
            onChange={(e) => setFormat(e.target.value as Format | "")}
          >
            <option value="">{t("ideasPage.rotate")}</option>
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {t(`content.format.${f}`)}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-muted">{t("ideasPage.generateHint")}</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("actions.cancel")}</Button>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {t("ideasPage.generate")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function NewIdeaDialog({
  channelId,
  open,
  onClose,
  onCreated,
}: {
  channelId: string;
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [angle, setAngle] = useState("");
  const [format, setFormat] = useState<Format>("LONG");
  const [thumb, setThumb] = useState("");
  const [promise, setPromise] = useState("");
  const [busy, setBusy] = useState(false);
  const withPromise = thumb.trim().length > 0 || promise.trim().length > 0;
  const ready =
    title.trim().length >= 5 &&
    angle.trim().length >= 5 &&
    (!withPromise || (thumb.trim().length > 0 && promise.trim().length >= 10));
  const submit = async () => {
    setBusy(true);
    try {
      await call(() =>
        api.POST("/api/v1/channels/{channel_id}/ideas", {
          params: { path: { channel_id: channelId } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: {
            title: title.trim(),
            angle: angle.trim(),
            format,
            packaging_promise: withPromise
              ? {
                  title_idea: title.trim(),
                  thumbnail_text_idea: thumb.trim(),
                  promise_statement: promise.trim(),
                }
              : null,
          },
        }),
      );
      toast(t("ideasPage.created"));
      setTitle("");
      setAngle("");
      setThumb("");
      setPromise("");
      onCreated();
      onClose();
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} title={t("ideasPage.newTitle")} onClose={onClose} testId="new-idea-dialog">
      <div className="space-y-3">
        <div>
          <label htmlFor="idea-title" className="block text-sm font-medium">
            {t("ideasPage.titleField")}
          </label>
          <input
            id="idea-title"
            className={inputCls}
            maxLength={100}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="idea-angle" className="block text-sm font-medium">
            {t("ideasPage.angle")}
          </label>
          <textarea
            id="idea-angle"
            rows={2}
            maxLength={500}
            className={inputCls}
            value={angle}
            onChange={(e) => setAngle(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="idea-format" className="block text-sm font-medium">
            {t("ideasPage.format")}
          </label>
          <select
            id="idea-format"
            className={inputCls}
            value={format}
            onChange={(e) => setFormat(e.target.value as Format)}
          >
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {t(`content.format.${f}`)}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-sm font-medium">{t("ideasPage.promise")}</legend>
          <label htmlFor="idea-thumb" className="block text-sm">
            {t("ideasPage.thumbText")}
          </label>
          <input
            id="idea-thumb"
            className={inputCls}
            maxLength={40}
            value={thumb}
            onChange={(e) => setThumb(e.target.value)}
          />
          <label htmlFor="idea-promise" className="mt-2 block text-sm">
            {t("ideasPage.promiseStatement")}
          </label>
          <input
            id="idea-promise"
            className={inputCls}
            maxLength={200}
            value={promise}
            onChange={(e) => setPromise(e.target.value)}
          />
        </fieldset>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("actions.cancel")}</Button>
          <Button variant="primary" disabled={!ready || busy} onClick={() => void submit()}>
            {t("ideasPage.add")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function IdeaCard({ idea, onChanged }: { idea: IdeaOut; onChanged: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [date, setDate] = useState(idea.calendar_date ?? "");
  const [reason, setReason] = useState("");
  const [asking, setAsking] = useState(false);
  const command = async (cmd: "shortlist" | "schedule" | "approve" | "discard") => {
    try {
      const out = await call(() =>
        api.POST("/api/v1/ideas/{idea_id}/commands/{cmd}", {
          params: { path: { idea_id: idea.id, cmd } },
          headers: { "Idempotency-Key": idempotencyKey() },
          body: {
            date: cmd === "schedule" ? date || null : null,
            override_reason: cmd === "approve" && reason.trim() ? reason.trim() : null,
          },
        }),
      );
      toast(t(`ideasPage.done.${cmd}`));
      setAsking(false);
      onChanged();
      if (cmd === "approve" && out.project_id) void navigate(`/projects/${out.project_id}/script`);
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const promise = idea.packaging_promise as {
    title_idea?: string;
    thumbnail_text_idea?: string;
    promise_statement?: string;
  } | null;
  const approvable = idea.state === "SHORTLISTED" || idea.state === "SCHEDULED";
  return (
    <li data-testid={`idea-${idea.id}`}>
      <Card title={idea.title}>
        <p className="text-sm" dir="auto">
          {idea.angle}
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <IdeaStateBadge state={idea.state} />
          <Badge tone="neutral">{t(`content.format.${idea.format}`)}</Badge>
          {idea.pillar && <Badge tone="info">{idea.pillar}</Badge>}
          <Badge tone="neutral">{t(`content.source.${idea.source}`)}</Badge>
          {idea.variation_kind && <Badge tone="info">{t(`trending.kinds.${idea.variation_kind}`)}</Badge>}
          {idea.calendar_date && <span className="text-muted">📅 {idea.calendar_date}</span>}
          {idea.expires_at && (
            <span className="text-muted">
              {t("ideasPage.expires", { date: new Date(idea.expires_at).toLocaleDateString() })}
            </span>
          )}
        </p>
        <div className="mt-2">
          <SimilarityBadge idea={idea} />
        </div>
        {promise?.promise_statement && (
          <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-xs" data-testid="promise">
            <span className="font-medium">{t("ideasPage.promise")}:</span> “{promise.thumbnail_text_idea}” —{" "}
            {promise.promise_statement}
          </p>
        )}
        {idea.owner_value_add_prompt && (
          <p className="mt-2 text-xs text-muted">
            <span className="font-medium">{t("ideasPage.yourPart")}</span> {idea.owner_value_add_prompt}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {idea.state === "SUGGESTED" && (
            <>
              <Button onClick={() => void command("shortlist")}>{t("ideasPage.shortlist")}</Button>
              <Button variant="ghost" onClick={() => void command("discard")}>
                {t("ideasPage.discard")}
              </Button>
            </>
          )}
          {idea.state === "SHORTLISTED" && (
            <span className="flex items-center gap-1">
              <label className="sr-only" htmlFor={`date-${idea.id}`}>
                {t("ideasPage.date")}
              </label>
              <input
                id={`date-${idea.id}`}
                type="date"
                className="rounded-lg border border-line bg-bg px-2 py-1 text-sm"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
              <Button disabled={!date} onClick={() => void command("schedule")}>
                {t("ideasPage.schedule")}
              </Button>
            </span>
          )}
          {approvable &&
            (idea.duplicate && !asking ? (
              <Button variant="primary" onClick={() => setAsking(true)}>
                {t("ideasPage.approve")}
              </Button>
            ) : (
              !idea.duplicate && (
                <Button variant="primary" onClick={() => void command("approve")}>
                  {t("ideasPage.approve")}
                </Button>
              )
            ))}
          {idea.project_id && (
            <Link className="text-sm text-accent underline" to={`/projects/${idea.project_id}/script`}>
              {t("ideasPage.openProject")}
            </Link>
          )}
        </div>
        {asking && (
          <div className="mt-3 space-y-2" data-testid="override">
            <label htmlFor={`reason-${idea.id}`} className="block text-sm font-medium">
              {t("ideasPage.reason")}
            </label>
            <textarea
              id={`reason-${idea.id}`}
              rows={2}
              className={inputCls}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                variant="primary"
                disabled={reason.trim().length < 20}
                onClick={() => void command("approve")}
              >
                {t("ideasPage.approveAnyway")}
              </Button>
              <Button variant="ghost" onClick={() => setAsking(false)}>
                {t("actions.cancel")}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </li>
  );
}

/** Page 9 — Idea Generator (Phase 7): every channel, from discovery, Build or onboarded on its own. */
export function IdeasPage() {
  const page = getPage("ideas");
  const { id } = useParams();
  const { channelId: selected } = useSelectedChannel();
  const channelId = id ?? selected ?? "";
  const name = useChannelName(channelId);
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [generating, setGenerating] = useState(false);
  const [adding, setAdding] = useState(false);
  const ideas = useQuery({
    queryKey: ["ideas", channelId, filter],
    enabled: channelId.length > 0,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/channels/{channel_id}/ideas", {
          params: {
            path: { channel_id: channelId },
            query: { limit: 100, ...(filter === "ALL" ? {} : { state: filter }) },
          },
        }),
      ),
  });
  const pillars = useQuery({
    queryKey: ["strategies", "channel", channelId],
    enabled: channelId.length > 0,
    queryFn: () => call(() => api.GET("/api/v1/strategies")),
  });
  const hasBlueprint = (pillars.data ?? []).some(
    (s) => s.channel_id === channelId && s.status === "APPROVED",
  );
  const refresh = () => void qc.invalidateQueries({ queryKey: ["ideas", channelId] });
  const list = ideas.data?.items ?? [];
  return (
    <div className="space-y-4" data-testid="page-ideas">
      <PageTitle page={page}>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={!channelId} onClick={() => setGenerating(true)}>
            {t("ideasPage.generate")}
          </Button>
          <Button disabled={!channelId} onClick={() => setAdding(true)}>
            {t("ideasPage.newIdea")}
          </Button>
        </div>
      </PageTitle>
      {name && <p className="text-sm text-muted">{t("ideasPage.forChannel", { name })}</p>}
      {pillars.data && !hasBlueprint && <NoBlueprintHint />}
      <div className="flex flex-wrap gap-1" role="group" aria-label={t("ideasPage.filter")}>
        {FILTERS.map((f) => (
          <Button
            key={f}
            variant={filter === f ? "primary" : "ghost"}
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
          >
            {f === "ALL" ? t("ideasPage.all") : t(`content.ideaState.${f}`)}
          </Button>
        ))}
      </div>
      {ideas.isPending && <LoadingSkeleton />}
      {ideas.isError && (
        <ProblemDisplay problem={asProblem(ideas.error)} onRetry={() => void ideas.refetch()} />
      )}
      {ideas.data && list.length === 0 && (
        <StateCard
          message={t("pages.ideas.empty")}
          actionLabel={t("pages.ideas.emptyAction")}
          onAction={() => setGenerating(true)}
        />
      )}
      {list.length > 0 && (
        <ul data-testid="state-success" className="grid gap-3 lg:grid-cols-2">
          {list.map((idea) => (
            <IdeaCard key={idea.id} idea={idea} onChanged={refresh} />
          ))}
        </ul>
      )}
      {generating && (
        <GenerateDialog channelId={channelId} open={generating} onClose={() => setGenerating(false)} />
      )}
      {adding && (
        <NewIdeaDialog
          channelId={channelId}
          open={adding}
          onClose={() => setAdding(false)}
          onCreated={refresh}
        />
      )}
    </div>
  );
}
