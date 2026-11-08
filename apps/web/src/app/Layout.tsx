import { useState } from "react";
import { Outlet } from "react-router";
import { Banners } from "../components/Banners";
import { MobileNav, Sidebar } from "../components/Navigation";
import { ScenarioSwitcher } from "../components/ScenarioSwitcher";
import { TopBar } from "../components/TopBar";
import { t } from "../i18n";

/** App shell (FRONTEND_SPECIFICATION §0.1). */
export function Layout() {
  const [channelId, setChannelId] = useState("ch-1");
  return (
    <div className="flex min-h-screen bg-bg text-fg">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-surface px-3 py-2 focus:not-sr-only focus:fixed focus:start-2 focus:top-2"
      >
        {t("app.skipToContent")}
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar channelId={channelId} onChannel={setChannelId} />
        <Banners channelId={channelId} />
        <main
          id="main"
          tabIndex={-1}
          className="mx-auto w-full max-w-[1440px] flex-1 p-4 pb-32 sm:p-6 sm:pb-16"
        >
          <Outlet />
        </main>
      </div>
      <MobileNav />
      <ScenarioSwitcher />
    </div>
  );
}
