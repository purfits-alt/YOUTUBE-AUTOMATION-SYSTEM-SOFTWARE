import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setScenario } from "./lib/scenario";
import { handlers } from "./mocks/handlers";
import { resetTestApi, testApiHandlers } from "./mocks/testApi";

export const server = setupServer(...testApiHandlers, ...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  resetTestApi();
  setScenario("success");
});
afterAll(() => server.close());
