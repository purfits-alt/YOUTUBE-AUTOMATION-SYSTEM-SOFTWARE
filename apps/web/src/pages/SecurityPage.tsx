import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { DataTable } from "../components/DataTable";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StateCard } from "../components/StateCard";
import { Badge, Button, Card } from "../components/ui";
import { t } from "../i18n";
import { api, call } from "../lib/api/client";
import { asProblem, LoadingSkeleton, PageTitle } from "./PageView";
import { getPage } from "./registry";

function fmt(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/** Page 30 — Audit & Security Center (real since Phase 3). */
export function SecurityPage() {
  const page = getPage("security");
  const log = useInfiniteQuery({
    queryKey: ["page", "security", "audit-log"],
    queryFn: ({ pageParam }) =>
      call(() =>
        api.GET("/api/v1/audit-log", {
          params: { query: { limit: 50, ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const events = useQuery({
    queryKey: ["page", "security", "events"],
    queryFn: () => call(() => api.GET("/api/v1/security-events", { params: { query: { limit: 50 } } })),
  });
  const verify = useMutation({ mutationFn: () => call(() => api.GET("/api/v1/audit-log/verify-chain")) });

  const rows = log.data?.pages.flatMap((p) => p.items) ?? [];
  const empty = log.data !== undefined && rows.length === 0;

  return (
    <div className="space-y-4" data-testid="page-security">
      <PageTitle page={page}>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            onClick={() => verify.mutate()}
            disabled={verify.isPending}
            data-testid="verify-chain"
          >
            {t("actions.verifyChain")}
          </Button>
        </div>
      </PageTitle>
      {verify.data && (
        <p data-testid="chain-result" role="status">
          {verify.data.ok ? (
            <Badge tone="ok">{t("security.chainOk", { count: verify.data.checked })}</Badge>
          ) : (
            <Badge tone="danger">
              {t("security.chainBroken", { id: verify.data.first_broken_id ?? "?" })}
            </Badge>
          )}
        </p>
      )}
      {verify.isError && <ProblemDisplay problem={asProblem(verify.error)} />}

      {log.isPending && <LoadingSkeleton />}
      {log.isError && <ProblemDisplay problem={asProblem(log.error)} onRetry={() => void log.refetch()} />}
      {empty && (
        <StateCard
          message={t("pages.security.empty")}
          actionLabel={t("pages.security.emptyAction")}
          onAction={() => verify.mutate()}
        />
      )}
      {!empty && rows.length > 0 && (
        <div data-testid="state-success" className="space-y-4">
          <Card title={t("security.auditLog")}>
            <DataTable
              caption={t("security.auditLog")}
              columns={[
                { key: "time", label: t("columns.time") },
                { key: "actor", label: t("columns.actor") },
                { key: "action", label: t("columns.action") },
                { key: "entity", label: t("columns.entity") },
              ]}
              rows={rows.map((r) => ({
                id: String(r.id),
                time: fmt(r.occurred_at),
                actor: `${r.actor_type}`,
                action: r.action,
                entity: `${r.entity_type} ${r.entity_id.slice(0, 8)}`,
              }))}
            />
            {log.hasNextPage && (
              <Button
                className="mt-3"
                onClick={() => void log.fetchNextPage()}
                disabled={log.isFetchingNextPage}
              >
                {t("security.loadMore")}
              </Button>
            )}
          </Card>
          <Card title={t("security.events")}>
            {events.data && events.data.items.length === 0 ? (
              <p className="text-sm text-muted">{t("security.noEvents")}</p>
            ) : (
              <DataTable
                caption={t("security.events")}
                columns={[
                  { key: "time", label: t("columns.time") },
                  { key: "kind", label: t("columns.kind") },
                  { key: "severity", label: t("columns.severity") },
                ]}
                rows={(events.data?.items ?? []).map((e) => ({
                  id: String(e.id),
                  time: fmt(e.occurred_at),
                  kind: e.kind,
                  severity:
                    e.severity === "INFO" ? "Info" : e.severity === "WARNING" ? "Warning" : "Critical",
                }))}
              />
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
