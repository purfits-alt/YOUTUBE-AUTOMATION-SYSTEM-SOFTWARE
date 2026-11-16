import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { Badge, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call } from "../../lib/api/client";
import { useSelectedChannel } from "../../lib/channel";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";

/** /projects — the menu link of Script Studio: the selected channel's video projects. */
export function ProjectsIndexPage() {
  const { channelId } = useSelectedChannel();
  const navigate = useNavigate();
  const projects = useQuery({
    queryKey: ["projects", channelId ?? "all"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects", {
          params: { query: { limit: 100, ...(channelId ? { channel_id: channelId } : {}) } },
        }),
      ),
  });
  const list = projects.data?.items ?? [];
  return (
    <div className="space-y-4" data-testid="page-projects">
      <PageTitle page={getPage("script")} />
      <p className="text-sm text-muted">{t("projectsPage.hint")}</p>
      {projects.isPending && <LoadingSkeleton />}
      {projects.isError && (
        <ProblemDisplay problem={asProblem(projects.error)} onRetry={() => void projects.refetch()} />
      )}
      {projects.data && list.length === 0 && (
        <StateCard
          message={t("projectsPage.empty")}
          actionLabel={t("projectsPage.emptyAction")}
          onAction={() => {
            if (channelId) void navigate(`/channels/${channelId}/ideas`);
          }}
        />
      )}
      {list.length > 0 && (
        <Card>
          <ul className="divide-y divide-line" data-testid="project-list">
            {list.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <Link
                  className="font-medium text-accent underline"
                  to={`/projects/${p.id}/script`}
                  dir="auto"
                >
                  {p.working_title}
                </Link>
                <span className="flex items-center gap-2 text-sm">
                  <Badge tone="neutral">{t(`content.format.${p.format}`)}</Badge>
                  <Badge tone="info">{t(`content.projectState.${p.state}`)}</Badge>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
