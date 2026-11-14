import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { Badge, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call } from "../../lib/api/client";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import { CandidateStatus, ScoreText } from "./common";

/** Menu entry for the Branding Studio: every blueprint, newest first; open one to edit it. */
export function BlueprintsIndexPage() {
  const page = getPage("branding");
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: ["strategies", "all"],
    queryFn: () => call(() => api.GET("/api/v1/strategies")),
  });
  return (
    <div className="space-y-4" data-testid="page-blueprints">
      <PageTitle page={page} />
      {list.isPending && <LoadingSkeleton />}
      {list.isError && <ProblemDisplay problem={asProblem(list.error)} onRetry={() => void list.refetch()} />}
      {list.data && list.data.length === 0 && (
        <StateCard
          message={t("indexPages.noBlueprints")}
          actionLabel={t("indexPages.toDiscovery")}
          onAction={() => void navigate("/discovery")}
        />
      )}
      {list.data && list.data.length > 0 && (
        <Card title={t("indexPages.blueprints")}>
          <ul className="divide-y divide-line" data-testid="blueprint-list">
            {list.data.map((s) => {
              const niche = (s.blueprint as { niche?: { name?: string } }).niche?.name ?? "—";
              return (
                <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <Link className="font-medium text-accent underline" to={`/strategies/${s.id}`}>
                    {niche}
                  </Link>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    {t("indexPages.version", { v: s.version })}
                    <Badge tone={s.status === "APPROVED" ? "ok" : s.status === "DRAFT" ? "neutral" : "info"}>
                      {t(`brandingPage.status.${s.status}`)}
                    </Badge>
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}

/** Menu entry for Niche Research: the niches of the latest discovery run; open one for its evidence. */
export function NichesIndexPage() {
  const page = getPage("niche");
  const navigate = useNavigate();
  const reports = useQuery({
    queryKey: ["niche-reports"],
    queryFn: () => call(() => api.GET("/api/v1/niches/reports")),
  });
  const latest = reports.data?.[0]?.id;
  const detail = useQuery({
    queryKey: ["niche-report", latest],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/niches/reports/{report_id}", { params: { path: { report_id: latest ?? "" } } }),
      ),
    enabled: Boolean(latest),
  });
  const failed = reports.isError ? reports : detail.isError ? detail : null;
  const candidates = detail.data?.candidates_list ?? [];
  return (
    <div className="space-y-4" data-testid="page-niches">
      <PageTitle page={page} />
      {(reports.isPending || (latest && detail.isPending)) && <LoadingSkeleton />}
      {failed && <ProblemDisplay problem={asProblem(failed.error)} onRetry={() => void failed.refetch()} />}
      {reports.data && (!latest || (detail.data && candidates.length === 0)) && (
        <StateCard
          message={t("indexPages.noNiches")}
          actionLabel={t("indexPages.toDiscovery")}
          onAction={() => void navigate("/discovery")}
        />
      )}
      {candidates.length > 0 && (
        <Card title={t("indexPages.niches")}>
          <ul className="divide-y divide-line" data-testid="niche-list">
            {candidates.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <Link className="font-medium text-accent underline" to={`/research/niches/${c.id}`}>
                  {c.name}
                </Link>
                <span className="flex items-center gap-2 text-sm">
                  <ScoreText c={c} />
                  <CandidateStatus status={c.status} />
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
