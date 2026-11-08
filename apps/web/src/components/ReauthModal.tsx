import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { t } from "../i18n";
import { api, call, ProblemError, setReauthHandler } from "../lib/api/client";
import { Dialog } from "./Dialog";
import { Button } from "./ui";

const schema = z.object({ password: z.string().min(1, t("reauth.wrong")) });
type Form = z.infer<typeof schema>;

interface Pending {
  resolve: () => void;
  reject: (e: Error) => void;
}

/**
 * Step-up re-authentication (FRONTEND_SPECIFICATION §0.4): a 403 REAUTH_REQUIRED opens this modal;
 * after a successful POST /auth/step-up the original request is retried automatically.
 */
export function ReauthProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const pending = useRef<Pending | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, reset, formState } = useForm<Form>({ resolver: zodResolver(schema) });

  useEffect(() => {
    setReauthHandler(
      () =>
        new Promise<void>((resolve, reject) => {
          pending.current = { resolve, reject };
          setServerError(null);
          reset({ password: "" });
          setOpen(true);
        }),
    );
    return () => setReauthHandler(null);
  }, [reset]);

  const close = () => {
    setOpen(false);
    pending.current?.reject(new Error("Re-authentication cancelled"));
    pending.current = null;
  };

  const onSubmit = handleSubmit(async ({ password }) => {
    try {
      await call(() => api.POST("/auth/step-up", { body: { password } }));
      setOpen(false);
      pending.current?.resolve();
      pending.current = null;
    } catch (e) {
      setServerError(e instanceof ProblemError ? (e.problem.detail ?? t("reauth.wrong")) : t("reauth.wrong"));
    }
  });

  const errorText = serverError ?? formState.errors.password?.message;
  return (
    <>
      {children}
      <Dialog open={open} title={t("reauth.title")} onClose={close} testId="reauth-modal">
        <form onSubmit={(e) => void onSubmit(e)} noValidate>
          <p className="text-sm">{t("reauth.body")}</p>
          <label className="mt-3 block text-sm font-medium" htmlFor="reauth-password">
            {t("reauth.password")}
          </label>
          <input
            id="reauth-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={errorText ? true : undefined}
            aria-describedby={errorText ? "reauth-error" : undefined}
            className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2"
            {...register("password")}
          />
          {errorText && (
            <p id="reauth-error" role="alert" className="mt-1 text-sm text-danger-text">
              {errorText}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <Button onClick={close}>{t("confirm.cancel")}</Button>
            <Button type="submit" variant="primary" disabled={formState.isSubmitting}>
              {t("reauth.submit")}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
