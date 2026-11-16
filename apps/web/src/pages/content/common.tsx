import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Badge, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, type ClaimOut, type IdeaOut } from "../../lib/api/client";

export const IDEA_STATE_TONE: Record<IdeaOut["state"], Tone> = {
  SUGGESTED: "info",
  SHORTLISTED: "warn",
  SCHEDULED: "warn",
  APPROVED: "ok",
  IN_PRODUCTION: "ok",
  PRODUCED: "neutral",
  DISCARDED: "neutral",
};

export const VERDICT_TONE: Record<ClaimOut["verdict"], Tone> = {
  SUPPORTED: "ok",
  OPINION: "info",
  UNSUPPORTED: "warn",
  CONTRADICTED: "danger",
};

export function IdeaStateBadge({ state }: { state: IdeaOut["state"] }) {
  return <Badge tone={IDEA_STATE_TONE[state]}>{t(`content.ideaState.${state}`)}</Badge>;
}

/** Similarity to the channel's earlier ideas (ADR-0029): duplicate needs a reason; paraphrase is a hint. */
export function SimilarityBadge({ idea }: { idea: IdeaOut }) {
  if (idea.duplicate)
    return (
      <Badge tone="danger">
        {t("content.duplicate", { title: idea.similar_to_title ?? "", pct: pct(idea.similarity_max) })}
      </Badge>
    );
  if (idea.maybe_same_idea)
    return (
      <Badge tone="warn">
        {t("content.maybeSame", { title: idea.similar_to_title ?? "", pct: pct(idea.similarity_max) })}
      </Badge>
    );
  return null;
}

export function pct(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "0";
  return String(Math.round(Number(value) * 100));
}

/** The channel's name from the channel list (already cached by the top bar). */
export function useChannelName(channelId: string | undefined): string {
  const channels = useQuery({
    queryKey: ["channels", "names"],
    queryFn: () => call(() => api.GET("/api/v1/channels", { params: { query: { limit: 200 } } })),
  });
  return channels.data?.items.find((c) => c.id === channelId)?.name ?? "";
}

/** Hint for channels without an approved blueprint (e.g. onboarded outside discovery). */
export function NoBlueprintHint() {
  return (
    <p className="text-xs text-muted">
      {t("content.noBlueprint")}{" "}
      <Link className="text-accent underline" to="/discovery">
        {t("content.buildBlueprint")}
      </Link>
    </p>
  );
}

export const FORMATS = ["LONG", "SHORT"] as const;
export type Format = (typeof FORMATS)[number];
