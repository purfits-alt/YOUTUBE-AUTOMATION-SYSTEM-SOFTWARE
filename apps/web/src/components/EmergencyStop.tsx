import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../i18n";
import { api, call, idempotencyKey, ProblemError } from "../lib/api/client";
import { useControls } from "../lib/useBackend";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./icons";
import { useToast } from "./Toasts";

/**
 * Emergency Stop (mock until Phase 5). Visible on every page. Stopping takes 2 clicks; clearing needs
 * step-up re-authentication (the API answers 403 REAUTH_REQUIRED and the ReauthModal opens).
 */
export function EmergencyStop({ compact = false }: { compact?: boolean }) {
  const controls = useControls();
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<"stop" | "clear" | null>(null);
  const [reason, setReason] = useState("");
  const active = controls.data?.emergency_stop.active ?? false;

  const stop = async () => {
    const key = idempotencyKey();
    const next = await call(() =>
      api.POST("/api/v1/system/emergency-stop", { body: { reason }, headers: { "Idempotency-Key": key } }),
    );
    qc.setQueryData(["controls"], next);
    setDialog(null);
    setReason("");
    toast(t("estop.stoppedToast"));
  };
  const clear = async () => {
    try {
      // Same key on the automatic retry after re-authentication (the first attempt stored nothing).
      const key = idempotencyKey();
      const next = await call(() =>
        api.POST("/api/v1/system/emergency-stop/clear", {
          body: { reason: "" },
          headers: { "Idempotency-Key": key },
        }),
      );
      qc.setQueryData(["controls"], next);
      toast(t("estop.clearedToast"));
    } catch (e) {
      if (e instanceof ProblemError) toast(e.problem.detail ?? e.problem.title, "danger");
    } finally {
      setDialog(null);
    }
  };

  return (
    <>
      <button
        type="button"
        data-testid="emergency-stop"
        aria-pressed={active}
        onClick={() => setDialog(active ? "clear" : "stop")}
        className={`inline-flex min-h-9 items-center gap-1.5 rounded-lg border-2 border-danger px-3 py-1 text-sm font-bold transition ${
          active
            ? "tf-pulse bg-danger text-white dark:text-black"
            : "bg-surface text-danger-text hover:bg-danger-soft dark:text-danger"
        }`}
      >
        <Icon name="stop" className="size-4" />
        <span className={compact ? "sr-only" : ""}>{active ? t("estop.active") : t("estop.button")}</span>
        {compact && active && <span aria-hidden="true">{t("estop.active")}</span>}
      </button>
      <ConfirmDialog
        open={dialog === "stop"}
        title={t("estop.confirmTitle")}
        body={t("estop.confirmBody")}
        confirmLabel={t("estop.confirm")}
        danger
        onConfirm={stop}
        onClose={() => setDialog(null)}
        testId="estop-dialog"
      >
        <label htmlFor="estop-reason" className="mt-3 block text-sm font-medium">
          {t("estop.reason")}
        </label>
        <textarea
          id="estop-reason"
          maxLength={500}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2 text-sm"
        />
      </ConfirmDialog>
      <ConfirmDialog
        open={dialog === "clear"}
        title={t("estop.clearTitle")}
        body={t("estop.clearBody")}
        confirmLabel={t("estop.clearConfirm")}
        onConfirm={clear}
        onClose={() => setDialog(null)}
        testId="estop-clear-dialog"
      />
    </>
  );
}
