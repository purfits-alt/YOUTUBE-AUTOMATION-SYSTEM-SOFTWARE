import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type LookupItem, type LookupOut } from "../../lib/api/client";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";

type Kind = LookupOut["kind"];
const num = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());

function youtubeUrl(i: LookupItem): string | null {
  if (i.video_id) return `https://www.youtube.com/watch?v=${encodeURIComponent(i.video_id)}`;
  if (i.channel_id) return `https://www.youtube.com/channel/${encodeURIComponent(i.channel_id)}`;
  return null;
}

/** One item, on its own card — never a table that compares channels (ADR-0015). */
function ItemCard({ i }: { i: LookupItem }) {
  const url = youtubeUrl(i);
  return (
    <li className="rounded-lg border border-line p-3 text-sm" data-testid="lookup-item">
      <p className="font-semibold">{i.title ?? "—"}</p>
      <p className="text-xs text-muted">
        {i.type === "video" ? t("lookupPage.video") : t("lookupPage.channel")}
        {i.channel_title ? ` · ${i.channel_title}` : ""}
        {i.handle ? ` · ${i.handle}` : ""}
        {i.published_at ? ` · ${new Date(i.published_at).toLocaleDateString()}` : ""}
        {i.duration ? ` · ${i.duration}` : ""}
      </p>
      {(i.view_count != null || i.subscriber_count != null) && (
        <p className="mt-1 text-xs">
          {i.view_count != null && t("lookupPage.views", { n: num(i.view_count) })}
          {i.subscriber_count != null && ` · ${t("lookupPage.subscribers", { n: num(i.subscriber_count) })}`}
          {i.video_count != null && ` · ${t("lookupPage.videos", { n: num(i.video_count) })}`}
        </p>
      )}
      {i.description_excerpt && <p className="mt-1 text-xs text-muted">{i.description_excerpt}</p>}
      {url && (
        <a
          className="mt-1 inline-block text-xs text-accent underline"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("lookupPage.open")}
        </a>
      )}
    </li>
  );
}

function Result({ r }: { r: LookupOut }) {
  return (
    <div className="space-y-2" data-testid={`lookup-${r.id}`}>
      <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone="neutral">{t(`lookupPage.kind.${r.kind}`)}</Badge>
        {r.query_key.replace(/^(id|handle|video|q):/, "")}
        {" · "}
        {t("lookupPage.kept", { date: new Date(r.expires_at).toLocaleDateString() })}
        {r.cached && <Badge tone="info">{t("lookupPage.cached")}</Badge>}
      </p>
      <ul className="space-y-2">
        {r.items.map((i, n) => (
          <ItemCard key={`${r.id}-${String(n)}`} i={i} />
        ))}
      </ul>
      <p className="text-xs text-muted" data-testid="lookup-notice">
        {r.notice}
      </p>
    </div>
  );
}

export function LookupPage() {
  const page = getPage("lookup");
  const toast = useToast();
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>("CHANNEL");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<LookupOut | null>(null);
  const [busy, setBusy] = useState(false);
  const recent = useQuery({
    queryKey: ["lookups"],
    queryFn: () => call(() => api.GET("/api/v1/lookups/youtube")),
  });
  const look = async () => {
    setBusy(true);
    try {
      const out = await call(() =>
        api.POST("/api/v1/lookups/youtube", {
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { kind, query },
        }),
      );
      setResult(out);
      void qc.invalidateQueries({ queryKey: ["lookups"] });
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  const list = recent.data ?? [];
  return (
    <div className="space-y-4" data-testid="page-lookup">
      <PageTitle page={page} />
      <p
        data-testid="policy-banner"
        className="tf-rise rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text"
      >
        {t("lookupPage.policy")}
      </p>
      <Card title={t("lookupPage.form")}>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="lookup-kind" className="block text-sm font-medium">
              {t("lookupPage.what")}
            </label>
            <select
              id="lookup-kind"
              className={inputCls}
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
            >
              {(["CHANNEL", "VIDEO", "SEARCH"] as const).map((k) => (
                <option key={k} value={k}>
                  {t(`lookupPage.kind.${k}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-0 flex-1">
            <label htmlFor="lookup-query" className="block text-sm font-medium">
              {t(`lookupPage.queryLabel.${kind}`)}
            </label>
            <input
              id="lookup-query"
              className={inputCls}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button variant="primary" disabled={busy || query.trim().length < 2} onClick={() => void look()}>
            {t("lookupPage.lookUp")}
          </Button>
        </div>
        {result && (
          <div className="mt-4" data-testid="lookup-result">
            <Result r={result} />
          </div>
        )}
      </Card>
      {recent.isPending && <LoadingSkeleton />}
      {recent.isError && (
        <ProblemDisplay problem={asProblem(recent.error)} onRetry={() => void recent.refetch()} />
      )}
      {recent.data && list.length === 0 && (
        <StateCard
          message={t("pages.lookup.empty")}
          actionLabel={t("pages.lookup.emptyAction")}
          onAction={() => document.getElementById("lookup-query")?.focus()}
        />
      )}
      {list.length > 0 && (
        <Card title={t("lookupPage.recent")}>
          <ul data-testid="state-success" className="space-y-4">
            {list.map((r) => (
              <li key={r.id}>
                <Result r={r} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
