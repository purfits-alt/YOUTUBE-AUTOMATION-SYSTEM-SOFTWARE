import { t } from "../i18n";
import type { Problem } from "../lib/api/client";
import { Button } from "./ui";

/** Error state: problem+json title/detail in plain language, code and request_id behind a toggle. */
export function ProblemDisplay({ problem, onRetry }: { problem: Problem; onRetry?: () => void }) {
  return (
    <div
      data-testid="state-error"
      role="alert"
      className="rounded-lg border border-danger bg-danger-soft p-4 text-danger-text"
    >
      <p className="font-semibold">{problem.title || t("states.errorTitle")}</p>
      {problem.detail && <p className="mt-1">{problem.detail}</p>}
      {problem.guards && problem.guards.length > 0 && (
        <ul className="mt-2 list-disc ps-5">
          {problem.guards.map((g) => (
            <li key={g.code}>
              {g.message}
              {g.fix_href && (
                <a className="ms-2 underline" href={g.fix_href}>
                  Fix
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer">{t("states.details")}</summary>
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3">
          <dt>{t("states.code")}</dt>
          <dd>
            <code>{problem.code}</code>
          </dd>
          {problem.request_id && (
            <>
              <dt>{t("states.requestId")}</dt>
              <dd>
                <code>{problem.request_id}</code>
              </dd>
            </>
          )}
        </dl>
      </details>
      {onRetry && (
        <Button className="mt-3" onClick={onRetry}>
          {t("states.retry")}
        </Button>
      )}
    </div>
  );
}
