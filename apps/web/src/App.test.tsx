import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App (Phase 1 placeholder)", () => {
  it("shows backend status when healthy", async () => {
    render(<App load={() => Promise.resolve({ status: "ok", version: "0.1.0" })} />);
    expect(screen.getByRole("heading", { name: "TubeForge is running" })).toBeInTheDocument();
    expect(await screen.findByTestId("backend-ok")).toHaveTextContent("ok");
  });

  it("shows an error state when the backend is offline", async () => {
    render(<App load={() => Promise.reject(new Error("Backend returned 503"))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend offline");
  });
});
