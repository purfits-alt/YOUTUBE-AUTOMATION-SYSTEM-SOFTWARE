import { useQueryClient } from "@tanstack/react-query";
import { t } from "../i18n";
import { api, call } from "../lib/api/client";
import { useMe } from "../lib/useBackend";
import { Icon } from "./icons";

export function UserMenu() {
  const me = useMe();
  const qc = useQueryClient();
  const name = me.data?.user.display_name ?? "";
  const signOut = async () => {
    await call(() => api.POST("/api/v1/auth/logout")).catch(() => undefined);
    // Show the sign-in screen at once, then drop every cached response of the old session.
    qc.setQueryData(["me"], null);
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  };
  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-sm text-muted 2xl:inline" title={t("user.signedInAs", { name })}>
        {name}
      </span>
      <button
        type="button"
        data-testid="sign-out"
        onClick={() => void signOut()}
        className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 text-sm hover:bg-surface-2"
      >
        <Icon name="publish" className="size-4 rotate-90" />
        <span className="sr-only sm:not-sr-only">{t("user.signOut")}</span>
      </button>
    </div>
  );
}
