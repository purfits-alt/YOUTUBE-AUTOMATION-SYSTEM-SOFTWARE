import type { RouteObject } from "react-router";
import { NotFound } from "../pages/NotFound";
import { OverviewPage } from "../pages/OverviewPage";
import { PageView } from "../pages/PageView";
import { PAGES } from "../pages/registry";
import { ChannelTrendingPage } from "../pages/ChannelTrendingPage";
import { SecurityPage } from "../pages/SecurityPage";
import { SettingsPage } from "../pages/SettingsPage";
import { AuthGate } from "./AuthGate";
import { Layout } from "./Layout";

/** Pages with their own component: Security and Settings (real API since Phase 3) and Channel Trending (US-4.6). */
const REAL_PAGES: Record<string, () => React.JSX.Element> = {
  security: () => <SecurityPage />,
  trending: () => <ChannelTrendingPage />,
  settings: () => <SettingsPage />,
};

export const routes: RouteObject[] = [
  {
    element: (
      <AuthGate>
        <Layout />
      </AuthGate>
    ),
    children: [
      ...PAGES.map((page) =>
        page.id === "overview"
          ? { index: true, element: <OverviewPage /> }
          : { path: page.path, element: REAL_PAGES[page.id]?.() ?? <PageView key={page.id} page={page} /> },
      ),
      { path: "*", element: <NotFound /> },
    ],
  },
];
