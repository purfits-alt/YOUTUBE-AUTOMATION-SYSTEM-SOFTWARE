import type en from "../i18n/en.json";

export type PageId = keyof typeof en.pages;
export type GroupKey = keyof typeof en.groups;
export type ColumnKey = keyof typeof en.columns;
export type ActionKey = keyof typeof en.actions;

export interface PageDef {
  id: PageId;
  /** Page number in FRONTEND_SPECIFICATION. */
  num: number;
  /** React Router path. */
  path: string;
  group: GroupKey;
  /** Main GET endpoint under /api/v1 (BACKEND_SPECIFICATION); `{id}` is filled from the route. */
  api: string;
  columns: readonly ColumnKey[];
  actions: readonly ActionKey[];
  /** Shows "Estimates with sources — not a promise…" (FRONTEND_SPECIFICATION §0.4). */
  safety: boolean;
  /** Pages 11–18 share the Project header. */
  projectScoped: boolean;
  /** Backed by the real API (packages/shared/openapi.json) rather than mock data. */
  real?: true;
}
