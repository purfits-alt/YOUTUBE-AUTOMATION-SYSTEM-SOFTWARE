import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setScenario } from "./lib/scenario";
import { contentHandlers, resetContentApi } from "./mocks/contentApi";
import { handlers } from "./mocks/handlers";
import { researchHandlers, resetResearchApi } from "./mocks/researchApi";
import { resetTestApi, testApiHandlers } from "./mocks/testApi";

export const server = setupServer(...testApiHandlers, ...researchHandlers, ...contentHandlers, ...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  resetTestApi();
  resetResearchApi();
  resetContentApi();
  setScenario("success");
});
afterAll(() => server.close());
