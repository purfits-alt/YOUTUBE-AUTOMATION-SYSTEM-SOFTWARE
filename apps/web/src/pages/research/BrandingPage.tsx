import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Dialog } from "../../components/Dialog";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { useToast } from "../../components/Toasts";
import { Badge, Button, Card, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, type StrategyOut } from "../../lib/api/client";
import { inputCls, problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import { ScoreFooter } from "./common";

interface Idea {
  title: string;
  format: "LONG" | "SHORT";
  pillar: string;
  angle: string;
}
interface Blueprint {
  niche: { name: string; language: string };
  name_ideas: { name: string; reason: string; availability_note: string }[];
  description: string;
  brand: {
    tone: string[];
    palette: { hex: string; role: string }[];
    contrast_pair: { text: string; background: string; ratio: number };
    fonts: { family: string; use: string; licence: string }[];
    logo_brief: string;
    banner_brief: string;
  };
  positioning: string;
  target_audience: { description: string; needs: string[] };
  pillars: { name: string; description: string }[];
  formats: { name: string; format: string; description: string; owner_role: string }[];
  calendar_30d: { day: number; idea_ref: number; format: string }[];
  ideas: Idea[];
  growth_strategy: string[];
  risks: { risk: string; severity: "LOW" | "MEDIUM" | "HIGH"; mitigation: string }[];
  footer: string;
}
const STATUS_TONE: Record<StrategyOut["status"], Tone> = {
  DRAFT: "info",
  PROPOSED: "warn",
  APPROVED: "ok",
  SUPERSEDED: "neutral",
  REJECTED: "neutral",
};

function ApproveDialog({
  open,
  names,
  onClose,
  onApprove,
}: {
  open: boolean;
  names: string[];
  onClose: () => void;
  onApprove: (name: string, test: boolean) => void;
}) {
  const [name, setName] = useState(names[0] ?? "");
  const [test, setTest] = useState(true);
  return (
    <Dialog open={open} title={t("brandingPage.approveTitle")} onClose={onClose} testId="approve-dialog">
      <div className="space-y-3">
        <p className="text-sm">{t("brandingPage.approveHint")}</p>
        <div>
          <label htmlFor="channel-name" className="block text-sm font-medium">
            {t("brandingPage.channelName")}
          </label>
          <input
            id="channel-name"
            list="name-ideas"
            className={inputCls}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <datalist id="name-ideas">
            {names.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={test}
            onChange={(e) => setTest(e.target.checked)}
          />
          {t("brandingPage.testChannel")}
        </label>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t("actions.cancel")}</Button>
          <Button variant="primary" disabled={name.trim().length === 0} onClick={() => onApprove(name, test)}>
            {t("brandingPage.approveCreate")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function BrandingPage() {
  const page = getPage("branding");
  const { id = "" } = useParams();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Blueprint | null>(null);
  const [approving, setApproving] = useState(false);
  const strategy = useQuery({
    queryKey: ["strategy", id],
    queryFn: () =>
      call(() => api.GET("/api/v1/strategies/{strategy_id}", { params: { path: { strategy_id: id } } })),
  });
  const s = strategy.data;
  useEffect(() => {
    if (s) setDraft(s.blueprint as unknown as Blueprint);
  }, [s]);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["strategy", id] });
  const editable = s?.status === "DRAFT";
  const save = async () => {
    if (!s || !draft) return;
    try {
      await call(() =>
        api.PATCH("/api/v1/strategies/{strategy_id}", {
          params: { path: { strategy_id: id }, header: { "If-Match": `"${s.etag}"` } },
          body: { blueprint: draft as unknown as Record<string, unknown> },
        }),
      );
      toast(t("brandingPage.saved"));
      refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const command = async (cmd: "propose" | "reject" | "new-version") => {
    try {
      const out = await call(() =>
        api.POST("/api/v1/strategies/{strategy_id}/commands/{cmd}", {
          params: { path: { strategy_id: id, cmd } },
        }),
      );
      if (cmd === "new-version") void navigate(`/strategies/${out.id}`);
      else refresh();
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const approve = async (name: string, test: boolean) => {
    try {
      const out = await call(() =>
        api.POST("/api/v1/strategies/{strategy_id}/commands/{cmd}", {
          params: { path: { strategy_id: id, cmd: "approve" } },
          body: { channel_name: name, is_test_channel: test },
        }),
      );
      setApproving(false);
      toast(t("brandingPage.approved", { name }));
      void qc.invalidateQueries({ queryKey: ["channels"] });
      if (out.channel_id) void navigate(`/channels/${out.channel_id}/onboarding`);
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const b = draft;
  return (
    <div className="space-y-4" data-testid="page-branding">
      <PageTitle page={page}>
        {s && (
          <div className="flex flex-wrap gap-2">
            {editable && (
              <>
                <Button onClick={() => void save()}>{t("brandingPage.save")}</Button>
                <Button
                  variant="primary"
                  disabled={s.problems.length > 0}
                  onClick={() => void command("propose")}
                >
                  {t("brandingPage.propose")}
                </Button>
              </>
            )}
            {s.status === "PROPOSED" && (
              <Button variant="primary" onClick={() => setApproving(true)}>
                {t("brandingPage.approve")}
              </Button>
            )}
            {(s.status === "DRAFT" || s.status === "PROPOSED") && (
              <Button variant="ghost" onClick={() => void command("reject")}>
                {t("brandingPage.reject")}
              </Button>
            )}
            {s.status !== "SUPERSEDED" && (
              <Button onClick={() => void command("new-version")}>{t("brandingPage.newVersion")}</Button>
            )}
          </div>
        )}
      </PageTitle>
      {strategy.isPending && <LoadingSkeleton />}
      {strategy.isError && (
        <ProblemDisplay problem={asProblem(strategy.error)} onRetry={() => void strategy.refetch()} />
      )}
      {s && b && (
        <div data-testid="state-success" className="space-y-4">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={STATUS_TONE[s.status]}>{t(`brandingPage.status.${s.status}`)}</Badge>
            {t("researchPage.blueprintVersion", { v: s.version })} · {b.niche.name} ({b.niche.language})
            {s.channel_id && (
              <Link className="text-accent underline" to={`/channels/${s.channel_id}/onboarding`}>
                {t("brandingPage.openChannel")}
              </Link>
            )}
          </p>
          {s.problems.length > 0 ? (
            <div
              data-testid="blueprint-problems"
              className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-text"
            >
              <p className="font-semibold">{t("brandingPage.problems", { n: s.problems.length })}</p>
              <ul className="list-disc pl-5">
                {s.problems.slice(0, 10).map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p data-testid="blueprint-ok" className="rounded-lg bg-ok-soft px-3 py-2 text-sm text-ok-text">
              {t("brandingPage.noProblems")}
            </p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t("brandingPage.names")}>
              <ul className="space-y-1 text-sm" data-testid="name-ideas">
                {b.name_ideas.map((n) => (
                  <li key={n.name}>
                    <span className="font-medium">{n.name}</span>{" "}
                    <span className="text-muted">— {n.reason}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">{b.name_ideas[0]?.availability_note}</p>
            </Card>
            <Card title={t("brandingPage.identity")}>
              <p className="text-sm">{t("brandingPage.tone", { words: b.brand.tone.join(", ") })}</p>
              <ul className="mt-2 flex flex-wrap gap-2" aria-label={t("brandingPage.palette")}>
                {b.brand.palette.map((c) => (
                  <li key={c.hex} className="flex items-center gap-1 text-xs">
                    <span
                      aria-hidden="true"
                      className="inline-block size-5 rounded border border-line"
                      style={{ background: c.hex }}
                    />
                    {c.hex} · {c.role}
                  </li>
                ))}
              </ul>
              <p
                className="mt-2 inline-block rounded px-2 py-1 text-sm font-semibold"
                style={{ color: b.brand.contrast_pair.text, background: b.brand.contrast_pair.background }}
              >
                {t("brandingPage.contrast", { ratio: b.brand.contrast_pair.ratio })}
              </p>
              <p className="mt-2 text-sm">
                {t("brandingPage.fonts")}:{" "}
                {b.brand.fonts.map((f) => `${f.family} (${f.use}, ${f.licence})`).join(" · ")}
              </p>
              <p className="mt-2 text-xs text-muted">{b.brand.logo_brief}</p>
              <p className="mt-1 text-xs text-muted">{b.brand.banner_brief}</p>
            </Card>
          </div>
          <Card title={t("brandingPage.description")}>
            <label htmlFor="bp-description" className="sr-only">
              {t("brandingPage.description")}
            </label>
            <textarea
              id="bp-description"
              className={`${inputCls} min-h-24`}
              readOnly={!editable}
              value={b.description}
              onChange={(e) => setDraft({ ...b, description: e.target.value })}
            />
            <label htmlFor="bp-positioning" className="mt-3 block text-sm font-medium">
              {t("brandingPage.positioning")}
            </label>
            <textarea
              id="bp-positioning"
              className={`${inputCls} min-h-20`}
              readOnly={!editable}
              value={b.positioning}
              onChange={(e) => setDraft({ ...b, positioning: e.target.value })}
            />
            <p className="mt-2 text-sm">
              <span className="font-medium">{t("brandingPage.audience")}:</span>{" "}
              {b.target_audience.description}
            </p>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t("brandingPage.pillars")}>
              <ul className="list-disc pl-5 text-sm">
                {b.pillars.map((p) => (
                  <li key={p.name}>
                    <span className="font-medium">{p.name}</span> — {p.description}
                  </li>
                ))}
              </ul>
            </Card>
            <Card title={t("brandingPage.formats")}>
              <ul className="list-disc pl-5 text-sm">
                {b.formats.map((f) => (
                  <li key={f.name}>
                    <span className="font-medium">{f.name}</span> ({f.format}) — {f.owner_role}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <Card title={t("brandingPage.ideas", { n: b.ideas.length })}>
            <div
              className="max-h-96 overflow-auto"
              tabIndex={0}
              role="region"
              aria-label={t("brandingPage.ideas", { n: b.ideas.length })}
            >
              <table className="w-full text-sm" data-testid="ideas-table">
                <thead className="text-left text-muted">
                  <tr>
                    <th className="py-1 pr-2">#</th>
                    <th className="py-1 pr-2">{t("brandingPage.idea")}</th>
                    <th className="py-1 pr-2">{t("brandingPage.format")}</th>
                    <th className="py-1">{t("brandingPage.pillar")}</th>
                  </tr>
                </thead>
                <tbody>
                  {b.ideas.map((idea, n) => (
                    <tr key={n} className="border-t border-line">
                      <td className="py-1 pr-2 text-muted">{n + 1}</td>
                      <td className="py-1 pr-2">
                        {editable ? (
                          <input
                            aria-label={t("brandingPage.ideaTitle", { n: n + 1 })}
                            className="w-full rounded border border-line bg-bg px-2 py-1"
                            value={idea.title}
                            onChange={(e) =>
                              setDraft({
                                ...b,
                                ideas: b.ideas.map((x, i) => (i === n ? { ...x, title: e.target.value } : x)),
                              })
                            }
                          />
                        ) : (
                          idea.title
                        )}
                      </td>
                      <td className="py-1 pr-2">{idea.format}</td>
                      <td className="py-1">{idea.pillar}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t("brandingPage.calendar")}>
              <ol
                className="max-h-64 space-y-1 overflow-auto text-sm"
                data-testid="calendar"
                tabIndex={0}
                aria-label={t("brandingPage.calendar")}
              >
                {[...b.calendar_30d]
                  .sort((x, y) => x.day - y.day)
                  .map((e) => (
                    <li key={`${String(e.day)}-${String(e.idea_ref)}`}>
                      {t("brandingPage.day", { d: e.day })}: {e.format} — {b.ideas[e.idea_ref]?.title ?? "?"}
                    </li>
                  ))}
              </ol>
            </Card>
            <Card title={t("brandingPage.risks")}>
              <ul className="space-y-2 text-sm">
                {b.risks.map((r) => (
                  <li key={r.risk}>
                    <Badge tone={r.severity === "HIGH" ? "danger" : r.severity === "MEDIUM" ? "warn" : "ok"}>
                      {t(`levels.${r.severity}`)}
                    </Badge>{" "}
                    {r.risk}
                    <p className="text-xs text-muted">{r.mitigation}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-sm font-medium">{t("brandingPage.growth")}</p>
              <ul className="list-disc pl-5 text-sm">
                {b.growth_strategy.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </Card>
          </div>
          <ScoreFooter text={b.footer} />
          <ApproveDialog
            open={approving}
            names={b.name_ideas.map((n) => n.name)}
            onClose={() => setApproving(false)}
            onApprove={(name, test) => void approve(name, test)}
          />
        </div>
      )}
    </div>
  );
}
