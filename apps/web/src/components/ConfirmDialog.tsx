import { useState, type ReactNode } from "react";
import { t } from "../i18n";
import { Dialog } from "./Dialog";
import { Button } from "./ui";

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  onConfirm,
  onClose,
  children,
  testId,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
  children?: ReactNode;
  testId?: string;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} title={title} onClose={onClose} {...(testId ? { testId } : {})}>
      <p className="text-sm">{body}</p>
      {children}
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={onClose} disabled={busy}>
          {t("confirm.cancel")}
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          disabled={busy}
          onClick={() => {
            setBusy(true);
            Promise.resolve(onConfirm()).finally(() => setBusy(false));
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
