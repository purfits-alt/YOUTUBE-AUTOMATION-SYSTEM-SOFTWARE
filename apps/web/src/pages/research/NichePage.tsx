import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, idempotencyKey } from "../../lib/api/client";
import { problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle, SafetyNote } from "../PageView";
import { getPage } from "../registry";
import { CandidateStatus, CONFIDENCE_TONE, LEVEL_TONE, ScoreFooter, ScoreText } from "./common";

export function NichePage() {
  const page = getPage("niche");
  const { candidateId = "" } = useParams();
  const toast = useToast();
  const qc = useQueryClient();
  const cand = useQuery({
    queryKey: ["niche-candidate", candidateId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/niches/candidates/{candidate_id}", {
          params: { path: { candidate_id: candidateId } },
        }),
      ),
  });
  const strategies = useQuery({
    queryKey: ["strategies", candidateId],
    queryFn: () =>
      call(() => api.GET("/api/v1/strategies", { params: { query: { niche_candidate_id: candidateId } } })),
    enabled: cand.isSuccess,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["niche-candidate", candidateId] });
  const command = async (cmd: "shortlist" | "dismiss") => {
    try {
      await call(() =>
        api.POST("/api/v1/niches/candidates/{candidate_id}/commands/{cmd}", {
          params: { path: { candidate_id: candidateId, cmd } },
        }),
      );
      refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const blueprint = async () => {
    try {
      await call(() =>
        api.POST("/api/v1/strategies", {
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { niche_candidate_id: candidateId, owner_notes: "" },
        }),
      );
      toast(t("researchPage.blueprintQueued"));
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const c = cand.data;
  return (
    <div className="space-y-4" data-testid="page-niche">
      <PageTitle page={page} />
      <SafetyNote />
      {cand.isPending && <LoadingSkeleton />}
      {cand.isError && <ProblemDisplay problem={asProblem(cand.error)} onRetry={() => void cand.refetch()} />}
      {c && (
        <div data-testid="state-success" className="space-y-4">
          <Card title={c.name}>
            <p className="text-sm">{c.summary}</p>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              {t("researchPage.col.score")}: <ScoreText c={c} /> <CandidateStatus status={c.status} />
              <Badge tone={LEVEL_TONE[c.inauthentic_risk]}>
                {t("researchPage.col.risk")}: {t(`levels.${c.inauthentic_risk}`)}
              </Badge>
              <Badge tone={LEVEL_TONE[c.production_difficulty]}>
                {t("researchPage.col.difficulty")}: {t(`levels.${c.production_difficulty}`)}
              </Badge>
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {c.status !== "SHORTLISTED" && c.status !== "CONVERTED" && (
                <Button onClick={() => void command("shortlist")}>{t("researchPage.shortlist")}</Button>
              )}
              {c.status !== "DISMISSED" && c.status !== "CONVERTED" && (
                <Button variant="ghost" onClick={() => void command("dismiss")}>
                  {t("researchPage.dismiss")}
                </Button>
              )}
              {c.status === "SHORTLISTED" && (
                <Button variant="primary" onClick={() => void blueprint()}>
                  {t("researchPage.generateBlueprint")}
                </Button>
              )}
            </div>
          </Card>
          <Card title={t("researchPage.breakdown")}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="criteria-table">
                <thead className="text-left text-muted">
                  <tr>
                    <th className="py-2 pr-3">{t("researchPage.col.criterion")}</th>
                    <th className="py-2 pr-3">{t("researchPage.col.value")}</th>
                    <th className="py-2 pr-3">{t("researchPage.col.weight")}</th>
                    <th className="py-2 pr-3">{t("researchPage.col.confidence")}</th>
                    <th className="py-2">{t("researchPage.col.evidence")}</th>
                  </tr>
                </thead>
                <tbody>
                  {c.criteria.map((x) => (
                    <tr key={x.code} className="border-t border-line align-top">
                      <td className="py-2 pr-3">{t(`criteria.${x.code}`)}</td>
                      <td className="py-2 pr-3 tabular-nums">{x.value}</td>
                      <td className="py-2 pr-3 tabular-nums">{x.weight}</td>
                      <td className="py-2 pr-3">
                        <Badge tone={CONFIDENCE_TONE[x.confidence]}>{t(`levels.${x.confidence}`)}</Badge>
                      </td>
                      <td className="py-2">
                        {x.evidence.length === 0 ? (
                          <span className="text-muted">{x.note ?? t("researchPage.noEvidence")}</span>
                        ) : (
                          <ul className="space-y-1">
                            {x.evidence.map((e) => (
                              <li key={e.source_document_id}>
                                <a
                                  className="text-accent underline"
                                  href={e.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  {e.title ?? e.url}
                                </a>
                                {e.quote && <q className="block text-xs text-muted">{e.quote}</q>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {c.originality_angles.length > 0 && (
              <div className="mt-3 text-sm">
                <p className="font-semibold">{t("researchPage.angles")}</p>
                <ul className="list-disc pl-5">
                  {c.originality_angles.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-3">
              <ScoreFooter text={c.footer} />
            </div>
          </Card>
          <Card title={t("researchPage.blueprints")}>
            {(strategies.data ?? []).length === 0 ? (
              <p className="text-sm text-muted" data-testid="no-blueprints">
                {t("researchPage.noBlueprints")}
              </p>
            ) : (
              <ul className="space-y-1" data-testid="blueprints">
                {(strategies.data ?? []).map((s) => (
                  <li key={s.id}>
                    <Link className="text-accent underline" to={`/strategies/${s.id}`}>
                      {t("researchPage.blueprintVersion", { v: s.version })}
                    </Link>{" "}
                    <Badge tone={s.status === "APPROVED" ? "ok" : "info"}>
                      {t(`brandingPage.status.${s.status}`)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
