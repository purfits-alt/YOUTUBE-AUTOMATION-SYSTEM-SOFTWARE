import { useEffect, useState } from "react";
import { fetchHealth, type HealthState } from "./health";

/**
 * Phase 1 placeholder. The full app shell (31 routes, Emergency Stop, banners) is Phase 2.
 */
export function App({ load = fetchHealth }: { load?: typeof fetchHealth }) {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    load()
      .then((health) => {
        if (active) setState({ kind: "ok", health });
      })
      .catch((err: unknown) => {
        if (active) setState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      active = false;
    };
  }, [load]);

  return (
    <main className="page">
      <h1>TubeForge is running</h1>
      <p className="subtitle">
        Owner-directed, free-to-run YouTube production studio — foundation build (Phase 1).
      </p>
      <section aria-live="polite" className="status">
        {state.kind === "loading" && <p>Checking the backend…</p>}
        {state.kind === "ok" && (
          <p data-testid="backend-ok">
            Backend: <strong>{state.health.status}</strong> · version {state.health.version}
          </p>
        )}
        {state.kind === "error" && (
          <p role="alert" data-testid="backend-error">
            Backend offline: {state.message}. Start it with <code>tubeforge.ps1 start</code>.
          </p>
        )}
      </section>
      <p>
        <a href="/readyz">Readiness checks</a>
      </p>
    </main>
  );
}
