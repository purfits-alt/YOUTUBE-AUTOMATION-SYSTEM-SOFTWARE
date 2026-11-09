import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StateCard } from "../components/StateCard";
import { Badge, Button, type Tone } from "../components/ui";
import { t } from "../i18n";
import { api, call, type NotificationOut } from "../lib/api/client";
import { asProblem, LoadingSkeleton, PageTitle } from "./PageView";
import { getPage } from "./registry";

const TONE: Record<NotificationOut["severity"], Tone> = { INFO: "info", WARNING: "warn", CRITICAL: "danger" };

/** Page 27 — Notifications Center (in-app list real since Phase 4; Telegram/e-mail targets in Phase 12). */
export function NotificationsPage() {
  const page = getPage("notifications");
  const qc = useQueryClient();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const list = useQuery({
    queryKey: ["notifications", "list", unreadOnly],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/notifications", {
          params: { query: { limit: 100, ...(unreadOnly ? { unread: true } : {}) } },
        }),
      ),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const read = async (id: string) => {
    await call(() =>
      api.POST("/api/v1/notifications/{notification_id}/read", { params: { path: { notification_id: id } } }),
    );
    await refresh();
  };
  const readAll = async () => {
    await call(() => api.POST("/api/v1/notifications/read-all"));
    await refresh();
  };
  const items = list.data?.items ?? [];
  return (
    <div className="space-y-4" data-testid="page-notifications">
      <PageTitle page={page}>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
            {t("notificationsPage.unreadOnly")}
          </label>
          <Button onClick={() => void readAll()}>{t("actions.markAllRead")}</Button>
        </div>
      </PageTitle>
      {list.isPending && <LoadingSkeleton />}
      {list.isError && <ProblemDisplay problem={asProblem(list.error)} onRetry={() => void list.refetch()} />}
      {list.data && items.length === 0 && (
        <StateCard
          message={t("pages.notifications.empty")}
          actionLabel={t("pages.notifications.emptyAction")}
          onAction={() => void list.refetch()}
        />
      )}
      {items.length > 0 && (
        <ul data-testid="state-success" className="space-y-2" aria-label={t("pages.notifications.title")}>
          {items.map((n) => (
            <li
              key={n.id}
              data-testid="notification"
              className={`tf-card flex flex-wrap items-start gap-3 rounded-xl border border-line p-4 ${
                n.read_at ? "bg-surface" : "bg-surface-2"
              }`}
            >
              <Badge tone={TONE[n.severity]}>{t(`notificationsPage.severity.${n.severity}`)}</Badge>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{n.title}</p>
                <p className="text-sm text-muted">{n.body}</p>
                <p className="mt-1 text-xs text-muted">
                  <time dateTime={n.created_at}>{new Date(n.created_at).toLocaleString()}</time>
                  {n.link && (
                    <>
                      {" · "}
                      <Link className="text-accent underline" to={n.link}>
                        {t("notificationsPage.open")}
                      </Link>
                    </>
                  )}
                </p>
              </div>
              {!n.read_at && <Button onClick={() => void read(n.id)}>{t("actions.markRead")}</Button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
