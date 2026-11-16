import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { App, makeQueryClient } from "../../app/App";
import { routes } from "../../app/routes";
import { content } from "../../mocks/contentApi";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<App router={router} queryClient={makeQueryClient()} />);
  return router;
}

describe("Idea Generator (real API)", () => {
  it("lists ideas with promise, similarity and owner prompt; shortlists, schedules and approves", async () => {
    const router = renderAt("/channels/ch-1/ideas");
    const first = await screen.findByTestId("idea-i-1");
    expect(within(first).getByTestId("promise")).toHaveTextContent("5 APPS, 1 WINNER");
    expect(first).toHaveTextContent("Your part: Which app did you keep");
    fireEvent.click(within(first).getByRole("button", { name: "Shortlist" }));
    expect(await screen.findByText("Shortlisted.")).toBeInTheDocument();
    await waitFor(() => expect(content.ideas[0]?.state).toBe("SHORTLISTED"));

    // The near-duplicate asks for a written reason before approval.
    const dup = screen.getByTestId("idea-i-2");
    expect(dup).toHaveTextContent("Same as “My student budget for 2026, explained” (91% alike)");
    fireEvent.click(within(dup).getByRole("button", { name: "Approve" }));
    const reason = within(dup).getByLabelText(/Why make it anyway/);
    const anyway = within(dup).getByRole("button", { name: "Approve with this reason" });
    expect(anyway).toBeDisabled();
    fireEvent.change(reason, { target: { value: "A yearly update with this year's real numbers." } });
    fireEvent.click(anyway);
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/p-101/script"));
  });

  it("adds an owner idea (forbidden promises refused) and queues generation", async () => {
    renderAt("/channels/ch-1/ideas");
    fireEvent.click(await screen.findByRole("button", { name: "New idea" }));
    const dialog = await screen.findByTestId("new-idea-dialog");
    fireEvent.change(within(dialog).getByLabelText("Title"), {
      target: { value: "A guaranteed budget trick" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Angle/), { target: { value: "My spending log" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add idea" }));
    expect(await screen.findByText(/makes a promise TubeForge cannot keep/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "My real student budget" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add idea" }));
    expect(await screen.findByText("Idea added.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Generate ideas" }));
    const gen = await screen.findByTestId("generate-dialog");
    fireEvent.click(within(gen).getByRole("button", { name: "Generate ideas" }));
    await waitFor(() => expect(content.generated).toBe(1));
  });
});

describe("Content Calendar (real API)", () => {
  it("shows scheduled ideas in the month and moves one by date", async () => {
    content.ideas = content.ideas.map((i) => (i.id === "i-3" ? { ...i, calendar_date: isoToday() } : i));
    renderAt("/calendar");
    const chip = await screen.findByTestId("cal-item-i-3");
    expect(within(chip).getByRole("link", { name: "Why octopuses dream" })).toHaveAttribute(
      "href",
      "/projects/p-101/script",
    );
    const next = isoToday(1);
    fireEvent.change(within(chip).getByLabelText(/Move “Why octopuses dream”/), { target: { value: next } });
    await waitFor(() => expect(content.ideas.find((i) => i.id === "i-3")?.calendar_date).toBe(next));
  });
});

function isoToday(plusDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + plusDays);
  return `${String(d.getFullYear())}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

describe("Script Studio (real API)", () => {
  it("shows the gates, timing, claims; value-add unlocks approval; owner edits make a new version", async () => {
    renderAt("/projects/p-101/script");
    const header = await screen.findByTestId("project-header");
    expect(within(header).getByText("Script review").closest("li")).toHaveAttribute("aria-current", "step");
    expect(within(header).getByTestId("packaging-promise")).toHaveTextContent("THEY DREAM?");
    expect(within(header).getByTestId("checks")).toHaveTextContent("Add your own value");
    const timing = await screen.findByTestId("timing");
    expect(timing).toHaveTextContent("12.4 s (aim 10–15 s)");
    expect(screen.getByTestId("findings")).toHaveTextContent("All craft checks pass.");
    expect(screen.getAllByText(/Your story goes here/).length).toBeGreaterThan(0);

    // A contradicted script fact can be accepted with a reason.
    fireEvent.click(screen.getByRole("button", { name: "Accept with a reason" }));
    const od = await screen.findByTestId("override-dialog");
    fireEvent.change(within(od).getByLabelText(/Why is it fine/), {
      target: { value: "I will say it is one lab study, not all octopuses." },
    });
    fireEvent.click(within(od).getByRole("button", { name: "Accept with a reason" }));
    await waitFor(() => expect(content.claims[1]?.owner_override_reason).toMatch(/one lab study/));

    // Approval is refused until the owner adds value; then it goes through.
    fireEvent.click(within(header).getByRole("button", { name: "Approve script" }));
    expect(await screen.findByText(/Add your own value: 0 of 1/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your experience"), {
      target: { value: "I watched our neighbour's octopus tank change colour at night." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByTestId("value-score")).toHaveTextContent("25 / 100"));

    // Owner edit → version 2.
    fireEvent.change(screen.getByLabelText("Payoff"), {
      target: { value: "What it may mean, in plain words." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save as new version" }));
    expect(await screen.findByText(/Saved as version 2/)).toBeInTheDocument();
    await waitFor(() => expect(content.versions.length).toBe(2));
    expect((content.versions[1]?.body as { payoff: string }).payoff).toBe(
      "What it may mean, in plain words.",
    );
  });
});
