import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "./DataTable";

describe("DataTable", () => {
  it("sorts by a column and exposes aria-sort", () => {
    render(
      <DataTable
        caption="Videos"
        columns={[
          { key: "title", label: "Title" },
          { key: "views", label: "Views" },
        ]}
        rows={[
          { id: "1", title: "B", views: 10 },
          { id: "2", title: "A", views: 300 },
        ]}
      />,
    );
    const header = screen.getByRole("columnheader", { name: /Views/ });
    expect(header).toHaveAttribute("aria-sort", "none");
    fireEvent.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "ascending");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("B");
    expect(rows[1]).toHaveTextContent("300");
  });

  it("renders booleans and status columns as badges with text", () => {
    render(
      <DataTable
        caption="x"
        columns={[
          { key: "status", label: "Status" },
          { key: "read", label: "Read" },
        ]}
        rows={[{ id: "1", status: "Passed", read: false }]}
      />,
    );
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
  });
});
