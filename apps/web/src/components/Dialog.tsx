import { useEffect, useId, useRef, type ReactNode } from "react";

/** Accessible modal built on the native <dialog> (focus trap, Esc to close). */
export function Dialog({
  open,
  title,
  onClose,
  children,
  testId,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    } else if (!open && el.open) {
      if (typeof el.close === "function") el.close();
      else el.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      data-testid={testId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface p-5 text-fg shadow-xl"
    >
      {open && (
        <>
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          <div className="mt-3">{children}</div>
        </>
      )}
    </dialog>
  );
}
