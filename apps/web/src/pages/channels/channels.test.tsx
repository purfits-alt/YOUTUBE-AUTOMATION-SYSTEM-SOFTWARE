import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { App, makeQueryClient } from "../../app/App";
import { routes } from "../../app/routes";
import { resetTestApi, testChannel } from "../../mocks/testApi";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<App router={router} queryClient={makeQueryClient()} />);
  return router;
}

describe("Channel Manager (real API)", () => {
  it("lists channels with state, mode and token badges, and the bell shows real counts", async () => {
    renderAt("/channels");
    const card = await screen.findByTestId("channel-card");
    expect(card).toHaveTextContent("Calm Science");
    expect(within(card).getByTestId("channel-state")).toHaveTextContent("Connected");
    expect(card).toHaveTextContent("YouTube connected");
    expect(await screen.findByTestId("bell-count")).toHaveTextContent("1");
  });

  it("validates and adds a channel, then opens its setup", async () => {
    const router = renderAt("/channels");
    await screen.findByTestId("channel-card");
    fireEvent.click(screen.getByRole("button", { name: "Add channel" }));
    const dialog = await screen.findByTestId("add-channel-dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create and start setup" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Enter a name");
    fireEvent.change(within(dialog).getByLabelText(/Channel name/), { target: { value: "Test Lab" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create and start setup" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/channels/ch-2/onboarding"));
  });

  it("shows the empty state", async () => {
    resetTestApi({ channels: [] });
    renderAt("/channels");
    expect(await screen.findByTestId("state-empty")).toBeInTheDocument();
    expect(screen.getAllByTestId("channel-switcher")[0]).toHaveTextContent("Add a channel");
  });
});

describe("Channel Onboarding (real API)", () => {
  it("shows the 10 steps with help links, saves the OAuth client and marks steps done", async () => {
    resetTestApi({ channels: [testChannel({ state: "ONBOARDING", oauth_status: "NOT_CONNECTED" })] });
    renderAt("/channels/ch-1/onboarding");
    await screen.findByTestId("step-VERIFY_PHONE");
    expect(screen.getAllByTestId(/^step-/)).toHaveLength(10);
    const verify = screen.getByTestId("step-VERIFY_PHONE");
    expect(within(verify).getByRole("link")).toHaveAttribute(
      "href",
      "https://support.google.com/youtube/answer/171664",
    );
    fireEvent.click(within(verify).getByRole("button", { name: "Mark step done" }));
    await waitFor(() =>
      expect(within(screen.getByTestId("step-VERIFY_PHONE")).getByText("Done")).toBeInTheDocument(),
    );

    const form = screen.getByTestId("oauth-client-form");
    fireEvent.change(within(form).getByLabelText("Client ID"), { target: { value: "not an id" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save OAuth client" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("apps.googleusercontent.com");
    fireEvent.change(within(form).getByLabelText("Client ID"), {
      target: { value: "123-abc.apps.googleusercontent.com" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Save OAuth client" }));
    expect(await screen.findByTestId("oauth-client-registered")).toHaveTextContent("TubeForge desktop");
    // System steps have no manual buttons.
    expect(
      within(screen.getByTestId("step-TEST_UPLOAD")).queryByRole("button", { name: "Mark step done" }),
    ).toBeNull();
  });

  it("runs the private test upload and shows progress until done", async () => {
    renderAt("/channels/ch-1/onboarding");
    const button = await screen.findByTestId("test-upload");
    fireEvent.click(button);
    const progress = await screen.findByTestId("upload-progress");
    await waitFor(() => expect(progress).toHaveTextContent("Done · 100%"), { timeout: 5000 });
    expect(within(progress).getByRole("link", { name: "Open in YouTube Studio" })).toHaveAttribute(
      "href",
      "https://studio.youtube.com/video/vid-1/edit",
    );
  });

  it("Notifications page marks everything read", async () => {
    renderAt("/notifications");
    expect(await screen.findByTestId("notification")).toHaveTextContent("sign in again");
    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mark read" })).toBeNull());
  });
});
