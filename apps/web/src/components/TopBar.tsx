import { useState } from "react";
import { Link } from "react-router";
import { t } from "../i18n";
import { applyTheme, readTheme, type ThemeChoice } from "../lib/theme";
import { useShell } from "../lib/useBackend";
import { EmergencyStop } from "./EmergencyStop";
import { GlobalSearch } from "./GlobalSearch";
import { Icon } from "./icons";
import { Badge } from "./ui";
import { UserMenu } from "./UserMenu";

function ThemeSelect() {
  const [theme, setTheme] = useState<ThemeChoice>(readTheme);
  return (
    <label className="flex items-center gap-1 text-sm">
      <span className="sr-only">{t("topbar.theme")}</span>
      <select
        data-testid="theme-select"
        value={theme}
        onChange={(e) => {
          const v = e.target.value as ThemeChoice;
          setTheme(v);
          applyTheme(v);
        }}
        className="min-h-9 rounded-md border border-line bg-surface px-2 text-sm"
      >
        <option value="system">{t("topbar.themeSystem")}</option>
        <option value="light">{t("topbar.themeLight")}</option>
        <option value="dark">{t("topbar.themeDark")}</option>
      </select>
    </label>
  );
}

function ChannelSwitcher({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const shell = useShell();
  const channels = shell.data?.channels ?? [];
  const current = channels.find((c) => c.id === selected) ?? channels[0];
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm">
        <span className="sr-only">{t("topbar.channel")}</span>
        <select
          data-testid="channel-switcher"
          value={current?.id ?? ""}
          onChange={(e) => onSelect(e.target.value)}
          className="min-h-9 max-w-40 rounded-md border border-line bg-surface px-2 text-sm"
        >
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {current && (
        <span data-testid="mode-badge">
          <Badge tone="info">{t(`modes.${current.mode}`)}</Badge>
        </span>
      )}
      {current?.private_only && (
        <span data-testid="private-only-badge">
          <Badge tone="ok">{t("badges.privateOnly")}</Badge>
        </span>
      )}
    </div>
  );
}

function QuotaMeter() {
  const shell = useShell();
  const yt = shell.data?.quota.youtube_default_pct ?? 0;
  const peak = shell.data?.quota.free_tier_peak_pct ?? 0;
  const label = t("topbar.quotaDetail", { youtube: yt, peak });
  return (
    <Link
      to="/usage"
      data-testid="quota-meter"
      className="hidden items-center gap-2 text-xs md:flex"
      title={label}
    >
      <span className="hidden text-muted 2xl:inline">{t("topbar.quota")}</span>
      <span
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.max(yt, peak)}
        className="relative block h-2 w-20 overflow-hidden rounded-full bg-surface-2"
      >
        <span
          className="absolute inset-y-0 start-0 bg-accent"
          style={{ width: `${String(Math.max(yt, peak))}%` }}
        />
      </span>
      <span className="tabular-nums">{Math.max(yt, peak)}%</span>
    </Link>
  );
}

function Bell() {
  const shell = useShell();
  const unread = shell.data?.unread_notifications ?? 0;
  return (
    <Link
      to="/notifications"
      data-testid="notification-bell"
      className="relative inline-flex min-h-9 min-w-9 items-center justify-center rounded-lg border border-line bg-surface hover:bg-surface-2"
    >
      <Icon name="bell" className="size-5" />
      <span className="sr-only">
        {t("topbar.notifications")}, {t("topbar.unread", { count: unread })}
      </span>
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="absolute -end-1 -top-1 rounded-full bg-danger px-1.5 text-xs font-bold text-white dark:text-black"
        >
          {unread}
        </span>
      )}
    </Link>
  );
}

export function TopBar({ channelId, onChannel }: { channelId: string; onChannel: (id: string) => void }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-md">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 sm:px-4">
        <span className="me-1 font-bold sm:hidden">{t("app.name")}</span>
        <EmergencyStop />
        <GlobalSearch />
        <div className="ms-auto flex items-center gap-2">
          <div className="hidden sm:block">
            <ChannelSwitcher selected={channelId} onSelect={onChannel} />
          </div>
          <QuotaMeter />
          <Bell />
          <div className="hidden sm:block">
            <ThemeSelect />
          </div>
          <UserMenu />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-line px-3 py-1.5 sm:hidden">
        <ChannelSwitcher selected={channelId} onSelect={onChannel} />
        <div className="ms-auto">
          <ThemeSelect />
        </div>
      </div>
    </header>
  );
}
