import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { App, makeQueryClient } from "../../app/App";
import { routes } from "../../app/routes";
import { research } from "../../mocks/researchApi";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<App router={router} queryClient={makeQueryClient()} />);
  return router;
}

describe("Channel Discovery (real API)", () => {
  it("shows candidates with score band, footer and the dropped list; shortlists and queues a blueprint", async () => {
    renderAt("/discovery");
    const table = await screen.findByTestId("candidates-table");
    expect(table).toHaveTextContent("Student budgets with real numbers");
    expect(table).toHaveTextContent("72.5 ± 10");
    expect(screen.getByTestId("score-footer")).toHaveTextContent("Not a prediction of views");
    expect(screen.getByTestId("safety-note")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Shortlist" }));
    const generate = await within(screen.getByTestId("candidates-table")).findByRole("button", {
      name: "Generate blueprint",
    });
    fireEvent.click(generate);
    expect(await screen.findByText(/Blueprint queued/)).toBeInTheDocument();
  });

  it("runs a discovery with 'let TubeForge suggest' and manages research sources", async () => {
    renderAt("/discovery");
    fireEvent.click(await screen.findByRole("button", { name: "Run discovery" }));
    const dialog = await screen.findByTestId("discovery-dialog");
    expect(within(dialog).getByLabelText("English")).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Start discovery" }));
    expect(await screen.findByText(/Discovery queued/)).toBeInTheDocument();
    const wiki = await screen.findByTestId("source-WIKIPEDIA_PAGEVIEWS");
    expect(wiki).toHaveTextContent("Terms not checked yet");
    fireEvent.click(within(wiki).getByRole("button", { name: "I checked the terms" }));
    await waitFor(() =>
      expect(screen.getByTestId("source-WIKIPEDIA_PAGEVIEWS")).toHaveTextContent("Terms checked"),
    );
  });

  it("shows the evidence behind each criterion on the niche page", async () => {
    renderAt("/research/niches/c-1");
    const table = await screen.findByTestId("criteria-table");
    expect(within(table).getByRole("link", { name: "Pageviews · Budget · en.wikipedia" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(table).toHaveTextContent("Downgraded to LOW");
    expect(await screen.findByTestId("blueprints")).toHaveTextContent("Blueprint v1");
  });
});

describe("Competitor Research (real API)", () => {
  it("shows the policy banner and one result with the not-combined notice", async () => {
    renderAt("/research/lookup");
    expect(await screen.findByTestId("policy-banner")).toHaveTextContent("never combined");
    expect(await screen.findByTestId("state-empty")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Channel link, @handle or ID"), {
      target: { value: "@BudgetBros" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    const result = await screen.findByTestId("lookup-result");
    expect(within(result).getAllByTestId("lookup-item")).toHaveLength(1);
    expect(result).toHaveTextContent("12,000 subscribers");
    expect(within(result).getByTestId("lookup-notice")).toHaveTextContent("not combined with others");
  });
});

describe("Trend Intelligence (real API)", () => {
  it("lists trends, keeps 'turn into idea' for Phase 7 and dismisses", async () => {
    renderAt("/trends");
    const card = await screen.findByTestId("trend-t-1");
    expect(card).toHaveTextContent("Signal 2.4");
    expect(within(card).getByRole("button", { name: "Turn into idea" })).toBeDisabled();
    fireEvent.click(within(card).getByRole("button", { name: "Dismiss" }));
    expect(await screen.findByTestId("state-empty")).toBeInTheDocument();
  });
});

describe("Channel Branding Studio (real API)", () => {
  it("edits a draft, proposes and approves it, which creates the channel", async () => {
    const router = renderAt("/strategies/st-9");
    expect(await screen.findByTestId("blueprint-ok")).toBeInTheDocument();
    expect(within(screen.getByTestId("ideas-table")).getByLabelText("Title of idea 50")).toHaveValue(
      "Idea number 50",
    );
    fireEvent.change(screen.getByLabelText("Channel description"), { target: { value: "My own budgets." } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(research.strategy.etag).toBe("e2"));
    expect((research.strategy.blueprint as { description: string }).description).toBe("My own budgets.");
    fireEvent.click(screen.getByRole("button", { name: "Propose" }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    const dialog = await screen.findByTestId("approve-dialog");
    expect(within(dialog).getByLabelText(/test channel/)).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve and create channel" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/channels/ch-1/onboarding"));
    expect(research.approvedChannel).toBe("Budget Lab 1");
  });
});
