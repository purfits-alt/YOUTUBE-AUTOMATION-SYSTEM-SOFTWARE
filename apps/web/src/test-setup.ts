import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setScenario } from "./lib/scenario";
import { handlers } from "./mocks/handlers";
import { researchHandlers, resetResearchApi } from "./mocks/researchApi";
import { resetTestApi, testApiHandlers } from "./mocks/testApi";

export const server = setupServer(...testApiHandlers, ...researchHandlers, ...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  resetTestApi();
  resetResearchApi();
  setScenario("success");
});
afterAll(() => server.close());
