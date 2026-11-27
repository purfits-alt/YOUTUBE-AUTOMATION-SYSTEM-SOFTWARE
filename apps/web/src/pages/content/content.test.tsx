import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { App, makeQueryClient } from "../../app/App";
import { routes } from "../../app/routes";
import { content } from "../../mocks/contentApi";
import { resetTestApi, testChannel } from "../../mocks/testApi";

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
    expect(await screen.findByTestId("owner-parts")).toHaveTextContent("Your parts (2) — optional");

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

describe("Script Studio while researching", () => {
  it("runs research again with extra search words", async () => {
    content.project = {
      ...content.project,
      state: "RESEARCHING",
      allowed_commands: ["retry-research", "pause", "cancel"],
      checks: [],
    };
    content.versions = [];
    renderAt("/projects/p-101/script");
    const box = await screen.findByTestId("retry-research");
    fireEvent.change(within(box).getByLabelText(/Extra search words/), {
      target: { value: "Code Llama, VS Code" },
    });
    fireEvent.click(within(box).getByRole("button", { name: "Research again" }));
    expect(await screen.findByText(/Research is running again/)).toBeInTheDocument();
  });
});

describe("Pipeline (ADR-0031)", () => {
  it("shows every station, the live job with its %, and what comes next", async () => {
    renderAt("/pipeline");
    const board = await screen.findByTestId("stations");
    const research = within(board).getByTestId("station-research");
    expect(within(research).getByTestId("box-inbox")).toHaveTextContent("from Approved idea");
    expect(within(research).getByTestId("box-progress")).toHaveTextContent(
      "In progress1Run a code assistant on your own PC · 35%",
    );
    expect(within(research).getByTestId("box-forwarded")).toHaveTextContent("to Check the research");
    // The script under review passed research and script writing: complete there, forwarded on.
    expect(within(research).getByTestId("box-complete")).toHaveTextContent("Complete1");
    const writing = within(board).getByTestId("station-script");
    expect(within(writing).getByTestId("box-forwarded")).toHaveTextContent(
      "Forwarded1to Approve the scriptWhy octopuses dream",
    );
    const review = within(board).getByTestId("station-script_review");
    expect(review).toHaveTextContent("You");
    expect(within(review).getByTestId("box-inbox")).toHaveTextContent(
      "Inbox1from Script writingWhy octopuses dream",
    );
    expect(within(board).getByTestId("station-storyboard")).toHaveTextContent("Phase 8");

    const working = screen.getByTestId("pipeline-p-102");
    expect(working).toHaveAttribute("data-activity", "WORKING");
    const bar = within(working).getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "35");
    expect(working).toHaveTextContent("Reading articles (4 of 9)");
    expect(working).toHaveTextContent("about 75 s left");
    expect(within(working).getByTestId("next")).toHaveTextContent("Check the research (your turn)");
    expect(within(working).getByRole("listitem", { current: "step" })).toHaveTextContent("Research: now");

    const waiting = screen.getByTestId("pipeline-p-101");
    expect(waiting).toHaveAttribute("data-activity", "YOUR_TURN");
    expect(within(waiting).getByTestId("next")).toHaveTextContent("Storyboard — arrives in Phase 8");
    expect(screen.getByTestId("pipeline-jobs")).toHaveTextContent("New ideas");
  });

  it("has a card per channel with its state, and the page follows the picked channel", async () => {
    resetTestApi({ channels: [testChannel(), testChannel({ id: "ch-2", name: "Urdu Kahaniyan" })] });
    renderAt("/pipeline");
    const cards = await screen.findByTestId("channel-cards");
    const calm = within(cards).getByTestId("channel-card-ch-1");
    expect(calm).toHaveAttribute("aria-pressed", "true");
    expect(calm).toHaveTextContent("Calm Science");
    expect(calm).toHaveTextContent("Active");
    expect(calm).toHaveTextContent("2 videos on the line");
    expect(calm).toHaveTextContent("1working");
    expect(calm).toHaveTextContent("1your turn");
    const urdu = within(cards).getByTestId("channel-card-ch-2");
    expect(urdu).toHaveTextContent("Setting up");
    expect(urdu).toHaveTextContent("0 videos on the line");
    expect(screen.getByRole("heading", { name: "State board — Calm Science" })).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-projects").children).toHaveLength(2);

    // Picking the other channel (here or in the top bar) switches the whole page.
    fireEvent.change(screen.getByLabelText("Channel", { selector: "#pipeline-channel" }), {
      target: { value: "ch-2" },
    });
    expect(await screen.findByRole("heading", { name: "State board — Urdu Kahaniyan" })).toBeInTheDocument();
    expect(await screen.findByText(/No videos are in production yet/)).toBeInTheDocument();
    expect(screen.queryByTestId("pipeline-projects")).not.toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId("channel-cards")).getByTestId("channel-card-ch-1"));
    expect(await screen.findByRole("heading", { name: "State board — Calm Science" })).toBeInTheDocument();
  });

  it("shows the live bar in Script Studio and on the projects list", async () => {
    renderAt("/projects/p-102/script");
    const live = await screen.findByTestId("project-progress");
    expect(within(live).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "35");
    expect(live).toHaveTextContent("Reading articles (4 of 9)");
  });

  it("writes the script again with an instruction", async () => {
    content.project = {
      ...content.project,
      state: "SCRIPTING",
      allowed_commands: ["retry-script", "pause", "cancel"],
      checks: [],
    };
    renderAt("/projects/p-101/script");
    const box = await screen.findByTestId("retry-script");
    fireEvent.change(within(box).getByLabelText(/Instruction for the new draft/), {
      target: { value: "Shorter hook" },
    });
    fireEvent.click(within(box).getByRole("button", { name: "Write again" }));
    expect(await screen.findByText(/The script is being written again/)).toBeInTheDocument();
  });
});

describe("Channel art (Phase 8 step A)", () => {
  it("draws logos and banners, picks one of each, and makes the watermark from the owner's logo", async () => {
    renderAt("/strategies/st-9");
    const panel = await screen.findByTestId("channel-art");
    fireEvent.change(await within(panel).findByLabelText("Banner tagline (optional)"), {
      target: { value: "Science, calmly" },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "Draw logo and banner" }));
    const logo2 = await within(panel).findByTestId("logo-2");
    await waitFor(() => expect(content.artRequests).toEqual([{ tagline: "Science, calmly" }]));
    expect(within(panel).getByTestId("banner-1")).toHaveTextContent("Bold centre");
    expect(within(panel).getAllByRole("link", { name: "Download PNG" }).length).toBe(6);

    fireEvent.click(within(logo2).getByRole("button", { name: "Pick this one" }));
    await waitFor(() =>
      expect(within(logo2).getByRole("button", { name: "Picked" })).toHaveAttribute("aria-pressed", "true"),
    );
    expect(content.art.chosen_logo?.variant).toBe(2);
    fireEvent.click(
      within(within(panel).getByTestId("banner-3")).getByRole("button", { name: "Pick this one" }),
    );
    await waitFor(() => expect(content.art.chosen_banner?.variant).toBe(3));

    // The watermark needs the owner's file and the "it is mine" confirmation.
    const mark = within(panel).getByTestId("watermark");
    const make = within(mark).getByRole("button", { name: "Make watermark" });
    expect(make).toBeDisabled();
    const file = new File([new Uint8Array([137, 80, 78, 71])], "semrs.png", { type: "image/png" });
    fireEvent.change(within(mark).getByLabelText("Your logo file"), { target: { files: [file] } });
    expect(make).toBeDisabled();
    fireEvent.click(within(mark).getByLabelText("This is my own brand logo"));
    fireEvent.click(make);
    await waitFor(() => expect(content.watermarkUploads).toEqual([{ type: "image/png", confirmed: true }]));
    expect(await within(mark).findByAltText("Your video watermark")).toBeInTheDocument();
  });

  it("Asset Library is empty until files are made", async () => {
    content.art = { ...content.art, logos: [], banners: [] };
    renderAt("/assets");
    expect(await screen.findByText(/The library is empty/)).toBeInTheDocument();
  });
});

describe("Your parts (owner decision 2026-11-27: optional, never read aloud)", () => {
  it("puts the owner's words in place of [[OWNER: …]]", async () => {
    renderAt("/projects/p-101/script");
    const parts = await screen.findByTestId("owner-parts");
    expect(parts).toHaveTextContent("the app you kept and why");
    const put = within(parts).getByRole("button", { name: "Put my words in" });
    expect(put).toBeDisabled();
    fireEvent.change(within(parts).getAllByPlaceholderText("Your own words (optional)")[1] as HTMLElement, {
      target: { value: "I kept the notebook app because it was the only one I opened daily." },
    });
    fireEvent.click(put);
    expect(await screen.findByText(/Saved as version 2/)).toBeInTheDocument();
    const saved = content.versions[1]?.body as { sections: { text: string }[] };
    expect(JSON.stringify(saved)).not.toContain("[[OWNER:");
    expect(saved.sections.map((x) => x.text)).toContain(
      "I kept the notebook app because it was the only one I opened daily.",
    );
  });

  it("suggests 3 options; a fill-in needs the owner's real details before it goes in", async () => {
    renderAt("/projects/p-101/script");
    const parts = await screen.findByTestId("owner-parts");
    fireEvent.click(within(parts).getAllByRole("button", { name: "Suggest 3 options" })[1] as HTMLElement);
    const options = await within(parts).findByTestId("part-options-1");
    expect(options).toHaveTextContent("Your sentence");
    expect(options).toHaveTextContent("Ask viewers");
    expect(options).toHaveTextContent("General line");
    const box = within(parts).getAllByPlaceholderText("Your own words (optional)")[1] as HTMLTextAreaElement;
    fireEvent.click(within(options).getByLabelText(/I kept ___ because ___/));
    expect(box.value).toBe("I kept ___ because ___.");
    const put = within(parts).getByRole("button", { name: "Put my words in" });
    expect(put).toBeDisabled();
    expect(within(parts).getByTestId("blanks-left")).toHaveTextContent(
      "TubeForge never invents your experience",
    );
    fireEvent.change(box, { target: { value: "I kept the notebook app because I opened it daily." } });
    expect(put).toBeEnabled();
    fireEvent.click(within(options).getByLabelText(/Which app would you keep/));
    expect(box.value).toBe("Which app would you keep?");
    fireEvent.click(put);
    expect(await screen.findByText(/Saved as version 2/)).toBeInTheDocument();
    expect(JSON.stringify(content.versions[1]?.body)).toContain("Which app would you keep?");
  });

  it("removes empty parts and keeps them as optional suggestions", async () => {
    renderAt("/projects/p-101/script");
    const parts = await screen.findByTestId("owner-parts");
    fireEvent.click(within(parts).getByRole("button", { name: "Remove my empty parts" }));
    expect(await screen.findByText(/Saved as version 2/)).toBeInTheDocument();
    const saved = content.versions[1]?.body as { owner_slots: { prompt: string }[] };
    expect(JSON.stringify(saved)).not.toContain("[[OWNER:");
    expect(saved.owner_slots.map((x) => x.prompt)).toContain("the app you kept and why");
    expect(await screen.findByTestId("owner-suggestions")).toHaveTextContent("the app you kept and why");
    expect(screen.queryByTestId("owner-parts")).not.toBeInTheDocument();
  });

  it("tells the owner to reopen an approved script that still has empty parts", async () => {
    content.project = {
      ...content.project,
      state: "STORYBOARDING",
      allowed_commands: ["reopen-script", "pause", "cancel"],
      checks: [],
    };
    renderAt("/projects/p-101/script");
    expect(await screen.findByTestId("reopen-hint")).toHaveTextContent("2 empty [[OWNER: …]] part(s)");
    expect(
      within(screen.getByTestId("project-header")).getByRole("button", { name: "Reopen the script" }),
    ).toBeInTheDocument();
  });
});
