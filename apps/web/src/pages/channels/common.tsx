import { Badge, type Tone } from "../../components/ui";
import { t } from "../../i18n";
import type { ChannelOut } from "../../lib/api/client";

const STATE_TONE: Record<ChannelOut["state"], Tone> = {
  PROPOSED: "neutral",
  APPROVED: "info",
  REJECTED: "neutral",
  ONBOARDING: "info",
  CONNECTED: "ok",
  ACTIVE: "ok",
  PAUSED: "warn",
  NEEDS_REAUTH: "danger",
  DISCONNECTING: "warn",
  DISCONNECTED: "neutral",
};

export function StateBadge({ state }: { state: ChannelOut["state"] }) {
  return (
    <span data-testid="channel-state">
      <Badge tone={STATE_TONE[state]}>{t(`channelStates.${state}`)}</Badge>
    </span>
  );
}

export function TokenBadge({
  channel,
}: {
  channel: Pick<ChannelOut, "oauth_status" | "oauth_expiring_soon">;
}) {
  if (channel.oauth_status === "ACTIVE" && channel.oauth_expiring_soon)
    return <Badge tone="warn">{t("channelsPage.tokenExpiring")}</Badge>;
  const tone: Tone =
    channel.oauth_status === "ACTIVE"
      ? "ok"
      : channel.oauth_status === "NOT_CONNECTED"
        ? "neutral"
        : "danger";
  return <Badge tone={tone}>{t(`channelsPage.token.${channel.oauth_status}`)}</Badge>;
}

export const inputCls = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm";

export function problemText(e: unknown): string {
  if (e && typeof e === "object" && "problem" in e) {
    const p = (e as { problem: { detail?: string | null; title: string } }).problem;
    return p.detail ?? p.title;
  }
  return t("states.errorTitle");
}
