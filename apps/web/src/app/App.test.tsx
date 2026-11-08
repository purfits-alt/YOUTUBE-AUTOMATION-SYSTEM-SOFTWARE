import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { setScenario } from "../lib/scenario";
import { resetTestApi } from "../mocks/testApi";
import { App, makeQueryClient } from "./App";
import { routes } from "./routes";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} queryClient={makeQueryClient()} />);
}

describe("app shell", () => {
  it("renders the overview with mocked data and the global elements", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Overview Dashboard" })).toBeInTheDocument();
    expect(await screen.findByTestId("state-success")).toBeInTheDocument();
    expect(screen.getByTestId("emergency-stop")).toHaveTextContent("Emergency Stop");
    expect(await screen.findAllByTestId("mode-badge")).not.toHaveLength(0);
    expect(screen.getAllByTestId("private-only-badge")[0]).toHaveTextContent("Private-only");
    expect(await screen.findByText(/Private-only mode is ON for Calm Science/)).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    setScenario("empty");
    renderAt("/approvals");
    expect(await screen.findByTestId("state-empty")).toHaveTextContent("All caught up");
  });

  it("shows problem+json errors with code and request id, and retries", async () => {
    setScenario("error");
    renderAt("/renders");
    const error = await screen.findByTestId("state-error");
    expect(error).toHaveTextContent("Service unavailable");
    expect(error).toHaveTextContent("MOCK_ERROR");
    expect(error).toHaveTextContent("req-mock-mock_error");
    setScenario("success");
    fireEvent.click(within(error).getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("state-success")).toBeInTheDocument();
  });

  it("shows a skeleton while loading", async () => {
    setScenario("loading");
    renderAt("/uploads");
    expect(await screen.findByTestId("state-loading")).toBeInTheDocument();
  });

  it("shows the project header on project pages", async () => {
    renderAt("/projects/p-101/script");
    const header = await screen.findByTestId("project-header");
    expect(header).toHaveTextContent("Why octopuses dream");
    expect(within(header).getByText("SCRIPTING").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("Emergency Stop: stop with a reason, then clearing needs re-authentication", async () => {
    renderAt("/");
    const button = await screen.findByTestId("emergency-stop");
    fireEvent.click(button);
    const dialog = await screen.findByTestId("estop-dialog");
    fireEvent.change(within(dialog).getByLabelText("Reason (optional)"), { target: { value: "testing" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Stop everything" }));
    expect(
      await screen.findByText(/Emergency Stop is active — all automation is paused. Reason: testing/),
    ).toBeInTheDocument();
    await waitFor(() => expect(button).toHaveTextContent("STOPPED"));

    fireEvent.click(button);
    const clear = await screen.findByTestId("estop-clear-dialog");
    fireEvent.click(within(clear).getByRole("button", { name: "Resume" }));
    const reauth = await screen.findByTestId("reauth-modal");
    await waitFor(() => expect(reauth).toHaveAttribute("open"));
    fireEvent.change(within(reauth).getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(within(reauth).getByRole("button", { name: "Confirm" }));
    expect(await within(reauth).findByRole("alert")).toHaveTextContent("not accepted");
    fireEvent.change(within(reauth).getByLabelText("Password"), { target: { value: "owner-password" } });
    fireEvent.click(within(reauth).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(button).toHaveTextContent("Emergency Stop"));
    expect(screen.queryByText(/all automation is paused/)).not.toBeInTheDocument();
  });

  it("opens global search with Ctrl+K and finds pages", async () => {
    renderAt("/");
    await screen.findByTestId("state-success");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = await screen.findByTestId("search-dialog");
    fireEvent.change(within(dialog).getByRole("searchbox"), { target: { value: "render" } });
    expect(await within(dialog).findByRole("button", { name: /Render Manager/ })).toBeInTheDocument();
  });

  it("shows a not-found page for unknown routes", async () => {
    renderAt("/nope");
    expect(await screen.findByTestId("page-not-found")).toBeInTheDocument();
  });

  it("shows the sign-in screen when signed out, rejects a wrong password, then opens the app", async () => {
    resetTestApi({ signedIn: false });
    renderAt("/");
    const form = await screen.findByTestId("login-form");
    fireEvent.change(within(form).getByLabelText("E-mail"), { target: { value: "owner@example.com" } });
    fireEvent.change(within(form).getByLabelText("Password"), { target: { value: "nope" } });
    fireEvent.click(within(form).getByRole("button", { name: "Sign in" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("not correct");
    fireEvent.change(within(form).getByLabelText("Password"), { target: { value: "right password" } });
    fireEvent.click(within(form).getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Overview Dashboard" })).toBeInTheDocument();
  });

  it("Settings saves with If-Match and shows the version conflict message", async () => {
    renderAt("/settings");
    const form = await screen.findByTestId("settings-form");
    await waitFor(() => expect(within(form).getByLabelText(/Disk budget/)).toHaveValue(200));
    fireEvent.change(within(form).getByLabelText(/Disk budget/), { target: { value: "150" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
    // The form still holds version 1 → the next save conflicts until reloaded.
    resetTestApi({ settings: { ...(await import("../mocks/testApi")).testSettings(), version: 5 } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByText(/changed in another window/)).toBeInTheDocument();
  });

  it("Security verifies the audit chain", async () => {
    renderAt("/security");
    await screen.findByTestId("state-success");
    expect(screen.getByText("auth.login")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("verify-chain"));
    expect(await screen.findByTestId("chain-result")).toHaveTextContent("2 rows intact");
  });

  it("Sign out returns to the sign-in screen", async () => {
    renderAt("/");
    fireEvent.click(await screen.findByTestId("sign-out"));
    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
  });
});
