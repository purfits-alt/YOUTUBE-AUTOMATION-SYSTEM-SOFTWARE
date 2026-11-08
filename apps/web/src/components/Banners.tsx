import { useState } from "react";
import { t } from "../i18n";
import { useShell } from "../lib/useShell";

function Banner({
  tone,
  children,
  onDismiss,
}: {
  tone: "danger" | "warn" | "info";
  children: string;
  onDismiss?: () => void;
}) {
  const cls =
    tone === "danger"
      ? "bg-danger-soft text-danger-text border-danger"
      : tone === "warn"
        ? "bg-warn-soft text-warn-text border-line"
        : "bg-info-soft text-info-text border-line";
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`flex items-start gap-3 border-b px-4 py-2 text-sm ${cls}`}
    >
      <span aria-hidden="true">{tone === "danger" ? "■" : tone === "warn" ? "!" : "i"}</span>
      <p className="flex-1">{children}</p>
      {onDismiss && (
        <button type="button" className="underline" onClick={onDismiss}>
          {t("banners.dismiss")}
        </button>
      )}
    </div>
  );
}

/** Global banners (FRONTEND_SPECIFICATION §0.1). Emergency Stop and Private-only are not dismissible. */
export function Banners({ channelId }: { channelId: string }) {
  const shell = useShell();
  const [dismissedToken, setDismissedToken] = useState(false);
  if (shell.isError) return <Banner tone="danger">{t("banners.offline")}</Banner>;
  const data = shell.data;
  if (!data) return null;
  const channel = data.channels.find((c) => c.id === channelId) ?? data.channels[0];
  const estop = data.controls.emergency_stop;
  return (
    <div data-testid="banners">
      {estop.active && <Banner tone="danger">{t("banners.estop", { reason: estop.reason ?? "—" })}</Banner>}
      {data.controls.publishing_kill_switch && <Banner tone="danger">{t("banners.killSwitch")}</Banner>}
      {channel?.private_only && (
        <Banner tone="info">{t("banners.privateOnly", { channel: channel.name })}</Banner>
      )}
      {channel?.token_expiring && !dismissedToken && (
        <Banner tone="warn" onDismiss={() => setDismissedToken(true)}>
          {t("banners.tokenExpiring", { channel: channel.name })}
        </Banner>
      )}
    </div>
  );
}
