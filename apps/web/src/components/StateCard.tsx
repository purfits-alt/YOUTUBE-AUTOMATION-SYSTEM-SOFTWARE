import { Link } from "react-router";
import { t } from "../i18n";
import { Lottie } from "./Lottie";
import { Button } from "./ui";

/** Empty state: one sentence + primary action + help link (FRONTEND_SPECIFICATION §0.3). */
export function StateCard({
  message,
  actionLabel,
  onAction,
}: {
  message: string;
  /** Leave out when there is nothing for the owner to press (e.g. a job is working). */
  actionLabel?: string | undefined;
  onAction?: (() => void) | undefined;
}) {
  return (
    <div
      data-testid="state-empty"
      className="tf-card tf-rise rounded-xl border border-dashed border-line bg-surface px-6 py-8 text-center"
    >
      <Lottie name="empty-box" className="mx-auto size-28" />
      <p className="mx-auto mt-2 max-w-prose">{message}</p>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
        {actionLabel && onAction && (
          <Button variant="primary" onClick={onAction}>
            {actionLabel}
          </Button>
        )}
        <Link to="/settings" className="text-sm text-accent underline">
          {t("states.emptyHelp")}
        </Link>
      </div>
    </div>
  );
}
