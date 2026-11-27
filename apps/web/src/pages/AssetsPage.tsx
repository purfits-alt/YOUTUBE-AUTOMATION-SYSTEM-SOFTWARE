import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { ProblemDisplay } from "../components/ProblemDisplay";
import { StateCard } from "../components/StateCard";
import { Badge, Card } from "../components/ui";
import { t } from "../i18n";
import { api, call } from "../lib/api/client";
import { useSelectedChannel } from "../lib/channel";
import { asProblem, LoadingSkeleton, PageTitle } from "./PageView";
import { getPage } from "./registry";

function size(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${String(Math.ceil(bytes / 1024))} KB`;
}

/** Page 25 — Asset Library (Phase 8 step A): every file with its rights record; only files with
 * rights can be downloaded or used in a video. */
export function AssetsPage() {
  const navigate = useNavigate();
  const { channelId } = useSelectedChannel();
  const assets = useQuery({
    queryKey: ["assets", channelId ?? "all"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/assets", {
          params: { query: { limit: 100, ...(channelId ? { channel_id: channelId } : {}) } },
        }),
      ),
  });
  const items = assets.data?.items ?? [];
  return (
    <div className="space-y-4" data-testid="page-assets">
      <PageTitle page={getPage("assets")} />
      <p className="text-sm text-muted">{t("assetsPage.hint")}</p>
      {assets.isPending && <LoadingSkeleton />}
      {assets.isError && (
        <ProblemDisplay problem={asProblem(assets.error)} onRetry={() => void assets.refetch()} />
      )}
      {assets.data && items.length === 0 && (
        <StateCard
          message={t("pages.assets.empty")}
          actionLabel={t("assetsPage.emptyAction")}
          onAction={() => void navigate("/strategies")}
        />
      )}
      {items.length > 0 && (
        <Card>
          <ul className="divide-y divide-line" data-testid="state-success">
            {items.map((a) => (
              <li
                key={a.id}
                className="flex flex-wrap items-center gap-3 py-2 text-sm"
                data-testid={`asset-${a.id}`}
              >
                {a.download_url && a.mime_type.startsWith("image/") ? (
                  <img
                    src={a.download_url}
                    alt=""
                    className="size-14 rounded border border-line object-contain"
                  />
                ) : (
                  <span className="size-14 rounded border border-dashed border-line" aria-hidden="true" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">
                    {t(`assetsPage.kind.${a.kind}`, { kind: a.kind })} ·{" "}
                    {a.width && a.height ? `${String(a.width)}×${String(a.height)} · ` : ""}
                    {size(a.size_bytes)}
                  </span>
                  <span className="block text-xs text-muted">
                    {t(`assetsPage.origin.${a.origin}`, { origin: a.origin })} ·{" "}
                    {new Date(a.created_at).toLocaleString()}
                  </span>
                  <span className="block text-xs">{a.licence ?? t("assetsPage.noRights")}</span>
                </span>
                {a.rights_basis ? (
                  <Badge tone={a.commercial_use_allowed ? "ok" : "warn"}>
                    {a.commercial_use_allowed ? t("assetsPage.commercialOk") : t("assetsPage.noCommercial")}
                  </Badge>
                ) : (
                  <Badge tone="danger">{t("assetsPage.noRights")}</Badge>
                )}
                {a.download_url && (
                  <a className="text-accent underline" href={a.download_url} download>
                    {t("channelArt.download")}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
