import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { applyTheme, readTheme } from "./lib/theme";
import "./styles.css";

applyTheme(readTheme());

/**
 * Phase 2: every /api/v1 call is answered by MSW mock handlers in the browser.
 * Phase 3 replaces them with the real backend (set VITE_MOCKS=off).
 */
async function startMocks(): Promise<void> {
  if (import.meta.env.VITE_DEMO === "on") {
    // Public demo: sample data for every page, served from a sub-folder (vite base "/demo/").
    const { demoWorker } = await import("./mocks/demo");
    await demoWorker.start({
      serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
      onUnhandledRequest: "bypass",
      quiet: true,
    });
    return;
  }
  if (import.meta.env.VITE_MOCKS === "off") return;
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass", quiet: true });
}

// If the mock worker cannot start (service workers blocked or unsupported), render anyway: real
// pages work, and mocked pages show their error state instead of a blank screen.
void startMocks()
  .catch(() => undefined)
  .then(() => {
    const root = document.getElementById("root");
    if (!root) throw new Error("#root element missing");
    createRoot(root).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  });
