import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Dialog } from "../../components/Dialog";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import {
  api,
  call,
  idempotencyKey,
  type CandidateOut,
  type ProfileOut,
  type ReportOut,
  type SourceOut,
} from "../../lib/api/client";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle, SafetyNote } from "../PageView";
import { getPage } from "../registry";
import {
  CandidateStatus,
  LANGUAGES,
  LEVEL_TONE,
  ScoreFooter,
  ScoreText,
  splitList,
  type Lang,
} from "./common";

const REPORT_TONE: Record<ReportOut["status"], Tone> = {
  QUEUED: "info",
  RUNNING: "info",
  DONE: "ok",
  FAILED: "danger",
  WAITING_QUOTA: "warn",
  STOPPED: "warn",
};
const CRITERIA = [
  "AUDIENCE_DEMAND",
  "SEARCH_INTEREST",
  "RISING_TOPICS",
  "EVERGREEN",
  "COMPETITION_LEVEL",
  "ADVERTISER_SUITABILITY",
  "PRODUCTION_FEASIBILITY",
  "ORIGINALITY_OPPORTUNITY",
  "LONG_FORM_POTENTIAL",
  "SHORTS_POTENTIAL",
  "INAUTHENTIC_RISK_INVERSE",
] as const;

function RunDialog({
  open,
  onClose,
  profiles,
  onStarted,
}: {
  open: boolean;
  onClose: () => void;
  profiles: ProfileOut[];
  onStarted: (id: string) => void;
}) {
  const toast = useToast();
  const [langs, setLangs] = useState<Lang[]>(["en"]);
  const [interests, setInterests] = useState("");
  const [avoid, setAvoid] = useState("");
  const [profile, setProfile] = useState("");
  const [busy, setBusy] = useState(false);
  const start = async () => {
    setBusy(true);
    try {
      const out = await call(() =>
        api.POST("/api/v1/niches/reports", {
          headers: { "Idempotency-Key": idempotencyKey() },
          body: {
            languages: langs,
            interests: splitList(interests),
            avoid: splitList(avoid),
            weight_profile_id: profile || null,
          },
        }),
      );
      toast(t("researchPage.started"));
      onStarted(out.id);
      onClose();
    } catch (e) {
      toast(problemText(e), "danger");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} title={t("researchPage.runTitle")} onClose={onClose} testId="discovery-dialog">
      <div className="space-y-3">
        <fieldset>
          <legend className="text-sm font-medium">{t("researchPage.languages")}</legend>
          <div className="mt-1 flex flex-wrap gap-3">
            {LANGUAGES.map((l) => (
              <label key={l} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={langs.includes(l)}
                  onChange={(e) => setLangs(e.target.checked ? [...langs, l] : langs.filter((x) => x !== l))}
                />
                {t(`researchPage.lang.${l}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <div>
          <label htmlFor="disc-interests" className="block text-sm font-medium">
            {t("researchPage.interests")}
          </label>
          <input
            id="disc-interests"
            className={inputCls}
            value={interests}
            placeholder={t("researchPage.interestsHint")}
            onChange={(e) => setInterests(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted">{t("researchPage.suggestHint")}</p>
        </div>
        <div>
          <label htmlFor="disc-avoid" className="block text-sm font-medium">
            {t("researchPage.avoid")}
          </label>
          <input
            id="disc-avoid"
            className={inputCls}
            value={avoid}
            onChange={(e) => setAvoid(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="disc-profile" className="block text-sm font-medium">
            {t("researchPage.profile")}
          </label>
          <select
            id="disc-profile"
            className={inputCls}
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
          >
            <option value="">{t("researchPage.defaultProfile")}</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("actions.cancel")}</Button>
          <Button variant="primary" disabled={busy || langs.length === 0} onClick={() => void start()}>
            {t("researchPage.start")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function Weights({
  reportId,
  profiles,
  onDone,
}: {
  reportId: string;
  profiles: ProfileOut[];
  onDone: () => void;
}) {
  const toast = useToast();
  const base = profiles.find((p) => p.is_default)?.weights ?? {};
  const [weights, setWeights] = useState<Record<string, number>>(base);
  useEffect(() => setWeights(profiles.find((p) => p.is_default)?.weights ?? {}), [profiles]);
  const rescore = async (body: { weights?: Record<string, number>; weight_profile_id?: string }) => {
    try {
      await call(() => api.POST("/api/v1/niches/rescore", { body: { report_id: reportId, ...body } }));
      toast(t("researchPage.rescored"));
      onDone();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <details className="rounded-xl border border-line p-3" data-testid="weights">
      <summary className="cursor-pointer text-sm font-semibold">{t("researchPage.weights")}</summary>
      <p className="mt-2 text-xs text-muted">{t("researchPage.weightsHint")}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {profiles.map((p) => (
          <Button key={p.id} onClick={() => void rescore({ weight_profile_id: p.id })}>
            {p.name}
          </Button>
        ))}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {CRITERIA.map((code) => (
          <label key={code} className="flex items-center justify-between gap-2 text-sm">
            <span>{t(`criteria.${code}`)}</span>
            <input
              type="number"
              min={0}
              max={15}
              step={0.5}
              aria-label={t(`criteria.${code}`)}
              className="w-20 rounded-lg border border-line bg-bg px-2 py-1 text-sm"
              value={weights[code] ?? 0}
              onChange={(e) => setWeights({ ...weights, [code]: Number(e.target.value) })}
            />
          </label>
        ))}
      </div>
      <Button className="mt-3" variant="primary" onClick={() => void rescore({ weights })}>
        {t("researchPage.rescore")}
      </Button>
    </details>
  );
}

function Candidates({ reportId, profiles }: { reportId: string; profiles: ProfileOut[] }) {
  const toast = useToast();
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["niche-report", reportId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/niches/reports/{report_id}", { params: { path: { report_id: reportId } } }),
      ),
    refetchInterval: (q) => (["QUEUED", "RUNNING"].includes(q.state.data?.status ?? "") ? 5000 : false),
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["niche-report", reportId] });
  const command = async (c: CandidateOut, cmd: "shortlist" | "dismiss") => {
    try {
      await call(() =>
        api.POST("/api/v1/niches/candidates/{candidate_id}/commands/{cmd}", {
          params: { path: { candidate_id: c.id, cmd } },
        }),
      );
      refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const blueprint = async (c: CandidateOut) => {
    try {
      await call(() =>
        api.POST("/api/v1/strategies", {
          headers: { "Idempotency-Key": idempotencyKey() },
          body: { niche_candidate_id: c.id, owner_notes: "" },
        }),
      );
      toast(t("researchPage.blueprintQueued"));
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  if (detail.isPending) return <LoadingSkeleton />;
  if (detail.isError)
    return <ProblemDisplay problem={asProblem(detail.error)} onRetry={() => void detail.refetch()} />;
  const r = detail.data;
  const list = r.candidates_list;
  return (
    <div className="space-y-3" data-testid="report-detail">
      <p className="text-sm">
        <Badge tone={REPORT_TONE[r.status]}>{t(`researchPage.status.${r.status}`)}</Badge>{" "}
        {r.documents != null && t("researchPage.documents", { n: r.documents })}
      </p>
      {r.error && <p className="text-sm text-danger-text">{r.error}</p>}
      {list.length === 0 ? (
        <p className="text-sm text-muted" data-testid="no-candidates">
          {["QUEUED", "RUNNING"].includes(r.status)
            ? t("researchPage.working")
            : t("researchPage.noCandidates")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="candidates-table">
            <thead className="text-left text-muted">
              <tr>
                <th className="py-2 pr-3">{t("researchPage.col.name")}</th>
                <th className="py-2 pr-3">{t("researchPage.col.score")}</th>
                <th className="py-2 pr-3">{t("researchPage.col.risk")}</th>
                <th className="py-2 pr-3">{t("researchPage.col.difficulty")}</th>
                <th className="py-2 pr-3">{t("researchPage.col.status")}</th>
                <th className="py-2">{t("researchPage.col.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.id} className="border-t border-line align-top" data-testid={`candidate-${c.id}`}>
                  <td className="py-2 pr-3">
                    <Link className="font-medium text-accent underline" to={`/research/niches/${c.id}`}>
                      {c.name}
                    </Link>
                    <p className="text-xs text-muted">
                      {c.language} · {c.summary}
                    </p>
                  </td>
                  <td className="py-2 pr-3">
                    <ScoreText c={c} />
                  </td>
                  <td className="py-2 pr-3">
                    <Badge tone={LEVEL_TONE[c.inauthentic_risk]}>{t(`levels.${c.inauthentic_risk}`)}</Badge>
                  </td>
                  <td className="py-2 pr-3">
                    <Badge tone={LEVEL_TONE[c.production_difficulty]}>
                      {t(`levels.${c.production_difficulty}`)}
                    </Badge>
                  </td>
                  <td className="py-2 pr-3">
                    <CandidateStatus status={c.status} />
                  </td>
                  <td className="space-x-1 py-2 whitespace-nowrap">
                    {c.status !== "CONVERTED" && c.status !== "SHORTLISTED" && (
                      <Button onClick={() => void command(c, "shortlist")}>
                        {t("researchPage.shortlist")}
                      </Button>
                    )}
                    {c.status !== "CONVERTED" && c.status !== "DISMISSED" && (
                      <Button variant="ghost" onClick={() => void command(c, "dismiss")}>
                        {t("researchPage.dismiss")}
                      </Button>
                    )}
                    {c.status === "SHORTLISTED" && (
                      <Button variant="primary" onClick={() => void blueprint(c)}>
                        {t("researchPage.generateBlueprint")}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {list.length > 0 && <Weights reportId={reportId} profiles={profiles} onDone={refresh} />}
      {(r.dropped.length > 0 || r.skipped.length > 0) && (
        <details className="text-sm">
          <summary className="cursor-pointer">
            {t("researchPage.dropped", { n: r.dropped.length + r.skipped.length })}
          </summary>
          <ul className="mt-1 list-disc pl-5 text-muted">
            {[...r.dropped, ...r.skipped].map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </details>
      )}
      <ScoreFooter text={list[0]?.footer ?? t("researchPage.footer")} />
    </div>
  );
}

function SourceRow({ s, onChanged }: { s: SourceOut; onChanged: () => void }) {
  const toast = useToast();
  const patch = async (body: { enabled?: boolean; terms_verified?: true }) => {
    try {
      await call(() =>
        api.PATCH("/api/v1/research-sources/{source_id}", { params: { path: { source_id: s.id } }, body }),
      );
      onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const test = async () => {
    try {
      const out = await call(() =>
        api.POST("/api/v1/research-sources/{source_id}/test", { params: { path: { source_id: s.id } } }),
      );
      toast(t("researchPage.testOk", { n: out.documents_stored }));
      onChanged();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const approvalTone: Tone =
    s.approval_status === "APPROVED" ? "ok" : s.approval_status === "BLOCKED" ? "danger" : "warn";
  return (
    <li
      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line p-3"
      data-testid={`source-${s.code}`}
    >
      <div className="min-w-0">
        <p className="font-medium break-all">{s.code}</p>
        <p className="text-xs text-muted">
          {s.allowed_hosts.join(", ") || t("researchPage.notFetched")} ·{" "}
          {t("researchPage.docs", { n: s.documents })}
        </p>
        <p className="mt-1 flex flex-wrap gap-1">
          <Badge tone={approvalTone}>{t(`researchPage.approval.${s.approval_status}`)}</Badge>
          <Badge tone={s.enabled ? "ok" : "neutral"}>
            {s.enabled ? t("researchPage.on") : t("researchPage.off")}
          </Badge>
          {s.terms_url &&
            (s.terms_verified_at ? (
              <Badge tone="ok">{t("researchPage.termsChecked", { date: s.terms_verified_at })}</Badge>
            ) : (
              <Badge tone="warn">{t("researchPage.termsNotChecked")}</Badge>
            ))}
        </p>
      </div>
      <div className="flex flex-wrap gap-1">
        {s.terms_url && (
          <a
            className="text-sm text-accent underline"
            href={s.terms_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("researchPage.terms")}
          </a>
        )}
        {s.terms_url && !s.terms_verified_at && (
          <Button onClick={() => void patch({ terms_verified: true })}>{t("researchPage.iChecked")}</Button>
        )}
        {s.approval_status !== "BLOCKED" && (
          <Button onClick={() => void patch({ enabled: !s.enabled })}>
            {s.enabled ? t("researchPage.switchOff") : t("researchPage.switchOn")}
          </Button>
        )}
        {s.fetchable && s.enabled && (
          <Button onClick={() => void test()}>{t("researchPage.testFetch")}</Button>
        )}
      </div>
    </li>
  );
}

function Sources() {
  const toast = useToast();
  const qc = useQueryClient();
  const sources = useQuery({
    queryKey: ["research-sources"],
    queryFn: () => call(() => api.GET("/api/v1/research-sources")),
  });
  const [slug, setSlug] = useState("");
  const [url, setUrl] = useState("");
  const refresh = () => void qc.invalidateQueries({ queryKey: ["research-sources"] });
  const add = async () => {
    try {
      await call(() => api.POST("/api/v1/research-sources", { body: { kind: "RSS", slug, url } }));
      setSlug("");
      setUrl("");
      toast(t("researchPage.feedAdded"));
      refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  return (
    <Card title={t("researchPage.sources")}>
      <p className="mb-3 text-sm text-muted">{t("researchPage.sourcesHint")}</p>
      {sources.isError && (
        <ProblemDisplay problem={asProblem(sources.error)} onRetry={() => void sources.refetch()} />
      )}
      <ul className="space-y-2" data-testid="sources">
        {(sources.data ?? []).map((s) => (
          <SourceRow key={s.id} s={s} onChanged={refresh} />
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-end gap-2" data-testid="add-feed">
        <div>
          <label htmlFor="feed-slug" className="block text-sm font-medium">
            {t("researchPage.feedName")}
          </label>
          <input
            id="feed-slug"
            className={inputCls}
            value={slug}
            placeholder="money-news"
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
          />
        </div>
        <div className="min-w-0 flex-1">
          <label htmlFor="feed-url" className="block text-sm font-medium">
            {t("researchPage.feedUrl")}
          </label>
          <input
            id="feed-url"
            className={inputCls}
            value={url}
            placeholder="https://…/feed.xml"
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
        <Button disabled={slug.length < 2 || !url.startsWith("https://")} onClick={() => void add()}>
          {t("researchPage.addFeed")}
        </Button>
      </div>
    </Card>
  );
}

export function DiscoveryPage() {
  const page = getPage("discovery");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string | undefined>();
  const qc = useQueryClient();
  const reports = useQuery({
    queryKey: ["niche-reports"],
    queryFn: () => call(() => api.GET("/api/v1/niches/reports")),
  });
  const profiles = useQuery({
    queryKey: ["weight-profiles"],
    queryFn: () => call(() => api.GET("/api/v1/niches/weight-profiles")),
  });
  const list = reports.data ?? [];
  const current = selected ?? list[0]?.id;
  return (
    <div className="space-y-4" data-testid="page-discovery">
      <PageTitle page={page}>
        <Button variant="primary" onClick={() => setOpen(true)}>
          {t("researchPage.run")}
        </Button>
      </PageTitle>
      <SafetyNote />
      {reports.isPending && <LoadingSkeleton />}
      {reports.isError && (
        <ProblemDisplay problem={asProblem(reports.error)} onRetry={() => void reports.refetch()} />
      )}
      {reports.data && list.length === 0 && (
        <StateCard
          message={t("pages.discovery.empty")}
          actionLabel={t("pages.discovery.emptyAction")}
          onAction={() => setOpen(true)}
        />
      )}
      {list.length > 0 && (
        <div data-testid="state-success" className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <Card title={t("researchPage.reports")}>
            <ul className="space-y-1" data-testid="reports">
              {list.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    aria-pressed={r.id === current}
                    onClick={() => setSelected(r.id)}
                    className={`w-full rounded-lg px-2 py-1.5 text-left text-sm ${r.id === current ? "bg-surface-2 font-semibold" : "hover:bg-surface-2"}`}
                  >
                    {new Date(r.created_at).toLocaleString()}
                    <span className="block">
                      <Badge tone={REPORT_TONE[r.status]}>{t(`researchPage.status.${r.status}`)}</Badge>{" "}
                      <span className="text-xs text-muted">
                        {r.interests.length ? r.interests.join(", ") : t("researchPage.suggested")}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={t("researchPage.candidates")}>
            {current && <Candidates reportId={current} profiles={profiles.data ?? []} />}
          </Card>
        </div>
      )}
      <Sources />
      <RunDialog
        open={open}
        onClose={() => setOpen(false)}
        profiles={profiles.data ?? []}
        onStarted={(id) => {
          setSelected(id);
          void qc.invalidateQueries({ queryKey: ["niche-reports"] });
        }}
      />
    </div>
  );
}
