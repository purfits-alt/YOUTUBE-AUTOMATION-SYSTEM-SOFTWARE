import type { RouteObject } from "react-router";
import { NotFound } from "../pages/NotFound";
import { OverviewPage } from "../pages/OverviewPage";
import { PageView } from "../pages/PageView";
import { PAGES } from "../pages/registry";
import { SecurityPage } from "../pages/SecurityPage";
import { SettingsPage } from "../pages/SettingsPage";
import { AuthGate } from "./AuthGate";
import { Layout } from "./Layout";

/** Pages backed by the real API since Phase 3 (the others still use mock data). */
const REAL_PAGES: Record<string, () => React.JSX.Element> = {
  security: () => <SecurityPage />,
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
