import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router";
import { t } from "../i18n";
import { GROUP_ORDER, PAGES, pageHref, getPage } from "../pages/registry";
import type { GroupKey, PageDef } from "../pages/types";
import { Dialog } from "./Dialog";
import { Icon, LogoMark, type IconName } from "./icons";

const GROUP_ICON: Record<GroupKey, IconName> = {
  home: "home",
  discover: "discover",
  channels: "channels",
  create: "create",
  publish: "publish",
  grow: "grow",
  library: "library",
  control: "control",
};

function shortName(page: PageDef): string {
  return t(`pages.${page.id}.title`)
    .split(/[\s&]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function itemClass(isActive: boolean, onDark: boolean, rail: boolean): string {
  const base = "group flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors";
  const tone = onDark
    ? isActive
      ? "bg-white/12 font-semibold text-white shadow-[inset_3px_0_0_#a897ff]"
      : "text-nav-fg hover:bg-white/6 hover:text-white"
    : isActive
      ? "bg-accent-soft font-semibold text-fg shadow-[inset_3px_0_0_var(--tf-accent)]"
      : "text-fg hover:bg-surface-2";
  return `${base} ${tone} ${rail ? "justify-center" : ""}`;
}

function NavItem({
  page,
  rail,
  onDark,
  onNavigate,
}: {
  page: PageDef;
  rail: boolean;
  onDark: boolean;
  onNavigate?: (() => void) | undefined;
}) {
  const title = t(`pages.${page.id}.title`);
  return (
    <NavLink
      to={pageHref(page)}
      end // exact match: "/channels" must not also light up on "/channels/:id/trending"
      onClick={onNavigate}
      title={rail ? title : undefined}
      className={({ isActive }) => itemClass(isActive, onDark, rail)}
    >
      {rail ? (
        <>
          <span aria-hidden="true" className="text-xs font-bold">
            {shortName(page)}
          </span>
          <span className="sr-only">{title}</span>
        </>
      ) : (
        <>
          <span
            aria-hidden="true"
            className={`w-5 shrink-0 text-end text-[11px] tabular-nums ${onDark ? "text-nav-muted" : "text-muted"}`}
          >
            {page.num}
          </span>
          <span className="truncate">{title}</span>
        </>
      )}
    </NavLink>
  );
}

/** Grouped navigation (FRONTEND_SPECIFICATION §0.2). */
export function NavGroups({
  rail = false,
  onDark = false,
  onNavigate,
}: {
  rail?: boolean;
  onDark?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <>
      {GROUP_ORDER.map((group) => {
        const pages = PAGES.filter((p) => p.group === group);
        const headingId = `nav-group-${group}${rail ? "-rail" : ""}${onNavigate ? "-drawer" : ""}`;
        return (
          <div key={group} className="mb-4">
            <h2
              id={headingId}
              className={`mb-1 flex items-center gap-2 px-2.5 text-[11px] font-semibold tracking-[0.12em] uppercase ${
                onDark ? "text-nav-muted" : "text-muted"
              } ${rail ? "sr-only" : ""}`}
            >
              <Icon name={GROUP_ICON[group]} className="size-3.5" />
              {t(`groups.${group}`)}
            </h2>
            <ul aria-labelledby={headingId} className="space-y-0.5">
              {pages.map((p) => (
                <li key={p.id}>
                  <NavItem page={p} rail={rail} onDark={onDark} onNavigate={onNavigate} />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </>
  );
}

/** Desktop sidebar (≥1024 px) and icon rail (640–1023 px). Hidden on mobile. Always dark ("studio"). */
export function Sidebar() {
  return (
    <>
      <nav
        aria-label={t("app.mainNav")}
        className="tf-sidebar sticky top-0 hidden h-screen w-68 shrink-0 overflow-y-auto p-3 lg:block"
      >
        <div className="mb-6 flex items-center gap-2.5 px-2 pt-1">
          <LogoMark className="size-9" />
          <div>
            <p className="text-lg leading-tight font-bold text-white">{t("app.name")}</p>
            <p className="text-[11px] text-nav-muted">{t("app.tagline")}</p>
          </div>
        </div>
        <NavGroups onDark />
      </nav>
      <nav
        aria-label={t("app.mainNav")}
        className="tf-sidebar sticky top-0 hidden h-screen w-16 shrink-0 overflow-y-auto p-2 sm:block lg:hidden"
      >
        <div className="mb-3 flex justify-center">
          <LogoMark className="size-8" />
        </div>
        <NavGroups rail onDark />
      </nav>
    </>
  );
}

const TAB_ICONS: Record<string, IconName> = {
  home: "home",
  approvals: "check",
  projects: "film",
  notifications: "bell",
};

/** Mobile bottom tab bar (Home, Approvals, Projects, Notifications, More) + drawer. */
export function MobileNav() {
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  useEffect(() => setDrawer(false), [location.pathname]);
  const tabs: { key: string; page: PageDef }[] = [
    { key: "home", page: getPage("overview") },
    { key: "approvals", page: getPage("approvals") },
    { key: "projects", page: getPage("script") },
    { key: "notifications", page: getPage("notifications") },
  ];
  return (
    <>
      <nav
        aria-label={t("app.mobileNav")}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur sm:hidden"
      >
        <ul className="grid grid-cols-5">
          {tabs.map(({ key, page }) => (
            <li key={key}>
              <NavLink
                to={pageHref(page)}
                end
                className={({ isActive }) =>
                  `flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs ${
                    isActive ? "font-bold text-accent" : "text-fg"
                  }`
                }
              >
                <Icon name={TAB_ICONS[key] ?? "home"} className="size-5" />
                {t(`mobileTabs.${key}`)}
              </NavLink>
            </li>
          ))}
          <li>
            <button
              type="button"
              data-testid="more-button"
              onClick={() => setDrawer(true)}
              className="flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-xs text-fg"
            >
              <Icon name="menu" className="size-5" />
              {t("mobileTabs.more")}
            </button>
          </li>
        </ul>
      </nav>
      <Dialog open={drawer} title={t("app.menu")} onClose={() => setDrawer(false)} testId="nav-drawer">
        <nav aria-label={t("app.mainNav")} className="max-h-[70vh] overflow-y-auto">
          <NavGroups onNavigate={() => setDrawer(false)} />
        </nav>
        <button type="button" className="mt-3 text-sm underline" onClick={() => setDrawer(false)}>
          {t("app.close")}
        </button>
      </Dialog>
    </>
  );
}
