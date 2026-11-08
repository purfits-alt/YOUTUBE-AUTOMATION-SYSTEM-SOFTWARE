import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { LogoMark } from "../components/icons";
import { Lottie } from "../components/Lottie";
import { Button } from "../components/ui";
import { t } from "../i18n";
import { api, call, ProblemError } from "../lib/api/client";
import { useMe } from "../lib/useBackend";

const loginSchema = z.object({
  email: z.string().trim().min(3, t("login.emailRequired")).max(254),
  password: z.string().min(1, t("login.passwordRequired")).max(1024),
});
const codeSchema = z.object({ code: z.string().trim().min(6, t("login.codeRequired")).max(20) });

function message(e: unknown): string {
  return e instanceof ProblemError ? (e.problem.detail ?? e.problem.title) : t("states.errorTitle");
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <main className="tf-hero grid min-h-screen place-items-center bg-bg px-4 py-10">
      <div className="tf-card tf-rise w-full max-w-md rounded-2xl border border-line bg-surface p-7">
        <div className="mb-5 flex items-center gap-3">
          <LogoMark className="size-10" />
          <div>
            <p className="text-xl font-bold">{t("app.name")}</p>
            <p className="text-xs text-muted">{t("app.tagline")}</p>
          </div>
        </div>
        {children}
      </div>
    </main>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string | undefined;
  children: ReactNode;
}) {
  return (
    <div className="mt-4">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-sm text-danger-text">
          {error}
        </p>
      )}
    </div>
  );
}

const inputCls = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2";

function LoginForm({ onDone }: { onDone: () => void }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof loginSchema>>({
    resolver: zodResolver(loginSchema),
  });
  const submit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      await call(() => api.POST("/api/v1/auth/login", { body: values }));
      onDone();
    } catch (e) {
      setServerError(message(e));
    }
  });
  return (
    <form onSubmit={(e) => void submit(e)} noValidate data-testid="login-form">
      <h1 className="text-2xl font-bold">{t("login.title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("login.subtitle")}</p>
      <Field id="login-email" label={t("login.email")} error={formState.errors.email?.message}>
        <input
          id="login-email"
          type="email"
          autoComplete="username"
          className={inputCls}
          {...register("email")}
        />
      </Field>
      <Field id="login-password" label={t("login.password")} error={formState.errors.password?.message}>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          className={inputCls}
          {...register("password")}
        />
      </Field>
      {serverError && (
        <p role="alert" className="mt-4 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-text">
          {serverError}
        </p>
      )}
      <Button type="submit" variant="primary" className="mt-6 w-full" disabled={formState.isSubmitting}>
        {t("login.submit")}
      </Button>
      <p className="mt-4 text-xs text-muted">{t("login.help")}</p>
    </form>
  );
}

function MfaForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof codeSchema>>({
    resolver: zodResolver(codeSchema),
  });
  const submit = handleSubmit(async ({ code }) => {
    setServerError(null);
    try {
      await call(() => api.POST("/api/v1/auth/mfa/verify", { body: { code } }));
      onDone();
    } catch (e) {
      setServerError(message(e));
    }
  });
  const signOut = async () => {
    await call(() => api.POST("/api/v1/auth/logout")).catch(() => undefined);
    await qc.invalidateQueries({ queryKey: ["me"] });
  };
  return (
    <form onSubmit={(e) => void submit(e)} noValidate data-testid="mfa-form">
      <h1 className="text-2xl font-bold">{t("login.mfaTitle")}</h1>
      <p className="mt-1 text-sm text-muted">{t("login.mfaSubtitle")}</p>
      <Field id="mfa-code" label={t("login.code")} error={formState.errors.code?.message}>
        <input
          id="mfa-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          className={inputCls}
          {...register("code")}
        />
      </Field>
      {serverError && (
        <p role="alert" className="mt-4 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger-text">
          {serverError}
        </p>
      )}
      <Button type="submit" variant="primary" className="mt-6 w-full" disabled={formState.isSubmitting}>
        {t("login.verify")}
      </Button>
      <button type="button" className="mt-3 text-sm text-accent underline" onClick={() => void signOut()}>
        {t("login.useOtherAccount")}
      </button>
    </form>
  );
}

/** Shows the sign-in screens until /auth/me confirms a full session (FRONTEND_SPECIFICATION §0.5). */
export function AuthGate({ children }: { children: ReactNode }) {
  const me = useMe();
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries();
  };
  if (me.isPending) {
    return (
      <main className="grid min-h-screen place-items-center bg-bg" aria-busy="true">
        <Lottie name="studio-orb" className="size-24" />
        <span className="sr-only">{t("states.loading")}</span>
      </main>
    );
  }
  if (me.isError) {
    return (
      <Frame>
        <p role="alert" className="text-sm text-danger-text">
          {t("banners.offline")}
        </p>
        <Button className="mt-4" onClick={() => void me.refetch()}>
          {t("states.retry")}
        </Button>
      </Frame>
    );
  }
  if (me.data === null) {
    return (
      <Frame>
        <LoginForm onDone={refresh} />
      </Frame>
    );
  }
  if (me.data.mfa_enabled && !me.data.mfa_passed) {
    return (
      <Frame>
        <MfaForm onDone={refresh} />
      </Frame>
    );
  }
  return <>{children}</>;
}
