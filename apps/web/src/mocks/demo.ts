import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";
import { researchHandlers } from "./researchApi";
import { testApiHandlers } from "./testApi";

/**
 * Public demo (tubeforge.semrs.com/demo, ADR-0028): every page of Phases 1–6 answered in the
 * visitor's browser with the same sample data the unit tests use. No server, no real logins, and
 * nothing leaves the browser; reloading the page resets everything.
 */
export const demoWorker = setupWorker(...testApiHandlers, ...researchHandlers, ...handlers);
