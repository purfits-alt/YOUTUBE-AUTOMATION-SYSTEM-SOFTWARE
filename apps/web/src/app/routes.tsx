import type { RouteObject } from "react-router";
import { NotFound } from "../pages/NotFound";
import { OverviewPage } from "../pages/OverviewPage";
import { PageView } from "../pages/PageView";
import { PAGES } from "../pages/registry";
import { Layout } from "./Layout";

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      ...PAGES.map((page) =>
        page.id === "overview"
          ? { index: true, element: <OverviewPage /> }
          : { path: page.path, element: <PageView key={page.id} page={page} /> },
      ),
      { path: "*", element: <NotFound /> },
    ],
  },
];
