import { useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { t } from "../i18n";
import { getScenario, SCENARIOS, setScenario, subscribeScenario, type Scenario } from "../lib/scenario";

/** Dev toolbar: forces empty / loading / error / success on every page (mock data only). */
export function ScenarioSwitcher() {
  const scenario = useSyncExternalStore(subscribeScenario, getScenario);
  const qc = useQueryClient();
  return (
    <div className="fixed end-3 bottom-18 z-40 rounded-md border border-line bg-surface px-2 py-1 text-xs shadow sm:bottom-3">
      <label className="flex items-center gap-1">
        <span>{t("scenario.label")}</span>
        <select
          data-testid="scenario-switcher"
          value={scenario}
          onChange={(e) => {
            setScenario(e.target.value as Scenario);
            void qc.resetQueries({
              predicate: (q) => q.queryKey[0] === "page" || q.queryKey[0] === "overview",
            });
          }}
          className="rounded border border-line bg-surface px-1 py-0.5"
        >
          {SCENARIOS.map((s) => (
            <option key={s} value={s}>
              {t(`scenario.${s}`)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
