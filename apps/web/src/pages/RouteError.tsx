import { useRouteError } from "react-router";
import { t } from "../i18n";

/** Shown instead of a blank page when a page crashes: what happened, and a way back. */
export function RouteError() {
  const error = useRouteError();
  const detail = error instanceof Error ? error.message : String(error);
  return (
    <div
      role="alert"
      className="m-6 space-y-3 rounded-xl border border-line bg-surface p-5"
      data-testid="route-error"
    >
      <h1 className="text-2xl font-bold">{t("routeError.title")}</h1>
      <p>{t("routeError.body")}</p>
      <p className="text-xs text-muted">
        {t("routeError.detail")} <code>{detail}</code>
      </p>
      <div className="flex gap-3">
        <button
          type="button"
          className="rounded-lg bg-accent px-3.5 py-1.5 text-sm font-medium text-accent-fg"
          onClick={() => window.location.reload()}
        >
          {t("routeError.reload")}
        </button>
        <a href="/" className="self-center text-sm text-accent underline">
          {t("notFound.home")}
        </a>
      </div>
    </div>
  );
}
