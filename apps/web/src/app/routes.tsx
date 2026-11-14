import type { RouteObject } from "react-router";
import { AgentsPage } from "../pages/agents/AgentsPage";
import { ChannelsPage } from "../pages/channels/ChannelsPage";
import { OnboardingPage } from "../pages/channels/OnboardingPage";
import { NotFound } from "../pages/NotFound";
import { NotificationsPage } from "../pages/NotificationsPage";
import { OverviewPage } from "../pages/OverviewPage";
import { PageView } from "../pages/PageView";
import { PAGES } from "../pages/registry";
import { ChannelTrendingPage } from "../pages/ChannelTrendingPage";
import { SecurityPage } from "../pages/SecurityPage";
import { SettingsPage } from "../pages/SettingsPage";
import { UsagePage } from "../pages/usage/UsagePage";
import { BrandingPage } from "../pages/research/BrandingPage";
import { DiscoveryPage } from "../pages/research/DiscoveryPage";
import { LookupPage } from "../pages/research/LookupPage";
import { BlueprintsIndexPage, NichesIndexPage } from "../pages/research/IndexPages";
import { NichePage } from "../pages/research/NichePage";
import { TrendsPage } from "../pages/research/TrendsPage";
import { AuthGate } from "./AuthGate";
import { Layout } from "./Layout";

/** Pages with their own component: real API pages (Phase 3: Security, Settings; Phase 4: Channels,
 * Onboarding, Notifications) and Channel Trending (US-4.6). */
const REAL_PAGES: Record<string, () => React.JSX.Element> = {
  channels: () => <ChannelsPage />,
  onboarding: () => <OnboardingPage />,
  notifications: () => <NotificationsPage />,
  usage: () => <UsagePage />,
  agents: () => <AgentsPage />,
  discovery: () => <DiscoveryPage />,
  niche: () => <NichePage />,
  trends: () => <TrendsPage />,
  lookup: () => <LookupPage />,
  branding: () => <BrandingPage />,
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
      { path: "/strategies", element: <BlueprintsIndexPage /> },
      { path: "/research/niches", element: <NichesIndexPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];
