import { Badge, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import type { CandidateOut } from "../../lib/api/client";

export const LANGUAGES = ["en", "es", "fr", "de", "ur"] as const;
export type Lang = (typeof LANGUAGES)[number];

export const LEVEL_TONE: Record<"LOW" | "MEDIUM" | "HIGH", Tone> = {
  LOW: "ok",
  MEDIUM: "warn",
  HIGH: "danger",
};
export const CONFIDENCE_TONE: Record<"LOW" | "MEDIUM" | "HIGH", Tone> = {
  LOW: "warn",
  MEDIUM: "info",
  HIGH: "ok",
};

/** "72.5 ± 10" — the band shows when much of the score rests on low-confidence criteria. */
export function ScoreText({ c }: { c: Pick<CandidateOut, "opportunity_score" | "band"> }) {
  const value = Number(c.opportunity_score).toFixed(1);
  return (
    <span className="font-semibold tabular-nums">
      {value}
      {c.band ? <span className="font-normal text-muted"> ± {Number(c.band).toFixed(0)}</span> : null}
    </span>
  );
}

export function CandidateStatus({ status }: { status: CandidateOut["status"] }) {
  const tone: Tone = status === "SHORTLISTED" ? "ok" : status === "CONVERTED" ? "info" : "neutral";
  return <Badge tone={tone}>{t(`researchPage.candidateStatus.${status}`)}</Badge>;
}

/** Fixed footer under every score (CHANNEL_DISCOVERY_SPEC §2). */
export function ScoreFooter({ text }: { text: string }) {
  return (
    <p data-testid="score-footer" className="text-xs text-muted">
      {text}
    </p>
  );
}

export function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length >= 2)
    .slice(0, 20);
}
