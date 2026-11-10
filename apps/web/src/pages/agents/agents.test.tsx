import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { App, makeQueryClient } from "../../app/App";
import { routes } from "../../app/routes";

function renderAt(path: string) {
  render(
    <App router={createMemoryRouter(routes, { initialEntries: [path] })} queryClient={makeQueryClient()} />,
  );
}

describe("Agent Control Center (real API)", () => {
  it("lists agents, runs the hello agent and shows the run", async () => {
    renderAt("/agents");
    const row = await screen.findByTestId("agent-T00_HELLO");
    expect(row).toHaveTextContent("Hello test agent");
    expect(row).toHaveTextContent("gemini-3.5-flash-lite → qwen2.5:1.5b");
    expect(await screen.findByTestId("runs-empty")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "Test run" }));
    const dialog = await screen.findByTestId("agent-run-dialog");
    fireEvent.change(within(dialog).getByLabelText("Name to greet"), { target: { value: "Ayesha" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Run" }));
    const table = await screen.findByTestId("runs-table");
    expect(table).toHaveTextContent("Done");
    fireEvent.click(within(table).getAllByRole("button")[0] as HTMLElement);
    expect(await screen.findByTestId("agent-run-details")).toHaveTextContent("Hello Ayesha");
  });

  it("edits limits with If-Match and keeps auditors on", async () => {
    renderAt("/agents");
    const row = await screen.findByTestId("agent-T00_HELLO");
    fireEvent.click(within(row).getByRole("button", { name: "Settings" }));
    const dialog = await screen.findByTestId("agent-config-dialog");
    fireEvent.change(within(dialog).getByLabelText("Runs per day"), { target: { value: "2" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /Move ollama:qwen2.5:1.5b up/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save config" }));
    await waitFor(() =>
      expect(within(screen.getByTestId("agent-T00_HELLO")).getByText("2")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("agent-T00_HELLO")).toHaveTextContent("qwen2.5:1.5b → gemini-3.5-flash-lite");

    fireEvent.click(
      within(screen.getByTestId("agent-A32_COST_MONITOR")).getByRole("button", { name: "Settings" }),
    );
    const audit = await screen.findByTestId("agent-config-dialog");
    expect(within(audit).getByLabelText("Agent is on")).toBeDisabled();
  });
});

describe("Cost & Usage Manager (real API)", () => {
  it("shows the zero-cost banner, saves a key and limits, and starts paid step 1", async () => {
    renderAt("/usage");
    expect(await screen.findByTestId("cost-banner")).toHaveTextContent(
      "$0.00 spent · 0 paid providers enabled",
    );
    const form = await screen.findByTestId("key-form-gemini");
    fireEvent.change(within(form).getByLabelText("gemini API key (write-only)"), {
      target: { value: "AIza-test-key-123" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Save key" }));
    expect(await screen.findByTestId("key-set-gemini")).toBeInTheDocument();
    const model = screen.getByTestId("provider-gemini:gemini-3.5-flash-lite");
    expect(within(model).getByRole("meter", { name: "Requests today" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    expect(model).toHaveTextContent("Placeholder limits");
    const paid = screen.getByTestId("paid-gemini:gemini-3.1-pro-preview");
    const step1 = within(paid).getByRole("button", { name: "Step 1: confirm" });
    expect(step1).toBeDisabled();
    fireEvent.click(within(paid).getByRole("checkbox"));
    fireEvent.click(step1);
    const step2 = await within(paid).findByTestId("paid-step2");
    expect(step2).toHaveTextContent("Type exactly: ENABLE PAID gemini:gemini-3.1-pro-preview");
    expect(within(step2).getByRole("button", { name: /Wait \d+ s/ })).toBeDisabled();
  });
});
