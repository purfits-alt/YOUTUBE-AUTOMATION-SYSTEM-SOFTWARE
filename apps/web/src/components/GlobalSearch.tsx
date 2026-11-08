import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { t } from "../i18n";
import { call, stubApi } from "../lib/api/client";
import { Dialog } from "./Dialog";
import { Icon } from "./icons";

/** Global search (Ctrl+K): channels, ideas, projects, assets, notifications and pages. */
export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const query = q.trim();
  const results = useQuery({
    queryKey: ["search", query],
    queryFn: () => call(() => stubApi.GET("/search", { params: { query: { q: query } } })),
    enabled: open && query.length > 0,
  });

  const go = (href: string) => {
    setOpen(false);
    setQ("");
    void navigate(href);
  };

  return (
    <>
      <button
        type="button"
        data-testid="search-button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-sm text-muted hover:bg-surface-2"
      >
        <Icon name="search" />
        <span className="sr-only sm:not-sr-only">{t("topbar.search")}</span>
        <kbd className="hidden rounded border border-line px-1 text-xs sm:inline" aria-hidden="true">
          {t("topbar.searchHint")}
        </kbd>
      </button>
      <Dialog open={open} title={t("search.title")} onClose={() => setOpen(false)} testId="search-dialog">
        <label htmlFor="global-search" className="sr-only">
          {t("search.placeholder")}
        </label>
        <input
          id="global-search"
          type="search"
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search.placeholder")}
          className="w-full rounded-md border border-line bg-bg px-3 py-2"
        />
        {query.length > 0 && (
          <ul className="mt-3 max-h-80 overflow-y-auto" aria-label={t("search.results")}>
            {results.data?.length === 0 && (
              <li className="py-2 text-sm text-muted">{t("search.noResults")}</li>
            )}
            {results.data?.map((hit) => (
              <li key={hit.kind + hit.href + hit.label}>
                <button
                  type="button"
                  onClick={() => go(hit.href)}
                  className="flex w-full items-center justify-between gap-3 rounded px-2 py-2 text-start hover:bg-surface-2"
                >
                  <span>{hit.label}</span>
                  <span className="text-xs text-muted">{hit.kind}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </>
  );
}
