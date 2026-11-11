import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { App, makeQueryClient } from "../app/App";
import { routes } from "../app/routes";

describe("pages still on preview data", () => {
  it("say plainly that a button did nothing yet", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/calendar"] });
    render(<App router={router} queryClient={makeQueryClient()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open item" }));
    expect(
      await screen.findByText(
        "Open item: preview only — this page is built in a later phase, so nothing was done.",
      ),
    ).toBeInTheDocument();
  });
});
