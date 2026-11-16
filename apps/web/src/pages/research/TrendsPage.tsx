import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey, type TrendOut } from "../../lib/api/client";
import { useSelectedChannel } from "../../lib/channel";
import { problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle, SafetyNote } from "../PageView";
import { getPage } from "../registry";
import { CONFIDENCE_TONE } from "./common";

export function TrendsPage() {
  const page = getPage("trends");
  const toast = useToast();
  const qc = useQueryClient();
  const { channelId } = useSelectedChannel();
  const trends = useQuery({
    queryKey: ["trends", channelId ?? "all"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/trends", { params: { query: channelId ? { channel_id: channelId } : {} } }),
      ),
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["trends"] });
  const scan = async () => {
    if (!channelId) return;
    try {
      await call(() =>
        api.POST("/api/v1/trends/scan", {
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { channel_id: channelId },
        }),
      );
      toast(t("trendsPage.scanQueued"));
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const command = async (item: TrendOut, cmd: "dismiss" | "to-idea") => {
    try {
      await call(() =>
        api.POST("/api/v1/trends/{trend_id}/commands/{cmd}", {
          params: { path: { trend_id: item.id, cmd } },
        }),
      );
      if (cmd === "to-idea") toast(t("trendsPage.ideaMade"));
      refresh();
      void qc.invalidateQueries({ queryKey: ["ideas"] });
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const list = trends.data ?? [];
  return (
    <div className="space-y-4" data-testid="page-trends">
      <PageTitle page={page}>
        <Button variant="primary" disabled={!channelId} onClick={() => void scan()}>
          {t("trendsPage.scan")}
        </Button>
      </PageTitle>
      <SafetyNote />
      {!channelId && <p className="text-sm text-muted">{t("trendsPage.noChannel")}</p>}
      {trends.isPending && <LoadingSkeleton />}
      {trends.isError && (
        <ProblemDisplay problem={asProblem(trends.error)} onRetry={() => void trends.refetch()} />
      )}
      {trends.data && list.length === 0 && (
        <StateCard
          message={t("pages.trends.empty")}
          actionLabel={t("pages.trends.emptyAction")}
          onAction={() => void scan()}
        />
      )}
      {list.length > 0 && (
        <ul data-testid="state-success" className="grid gap-3 md:grid-cols-2">
          {list.map((item) => (
            <li key={item.id} data-testid={`trend-${item.id}`}>
              <Card title={item.topic}>
                <p className="text-sm">{item.summary}</p>
                <p className="mt-2 flex flex-wrap gap-2 text-xs">
                  <Badge tone="info">
                    {t("trendsPage.strength", { s: Number(item.signal_strength).toFixed(1) })}
                  </Badge>
                  <Badge tone={CONFIDENCE_TONE[item.confidence]}>{t(`levels.${item.confidence}`)}</Badge>
                  <span className="text-muted">
                    {t("trendsPage.expires", { date: new Date(item.expires_at).toLocaleDateString() })}
                  </span>
                </p>
                {item.sources.length > 0 && (
                  <ul className="mt-2 text-xs">
                    {item.sources.map((s) => (
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
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button
                    variant="primary"
                    disabled={!item.channel_id}
                    onClick={() => void command(item, "to-idea")}
                  >
                    {t("trendsPage.toIdea")}
                  </Button>
                  <Button onClick={() => void command(item, "dismiss")}>{t("trendsPage.dismiss")}</Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
