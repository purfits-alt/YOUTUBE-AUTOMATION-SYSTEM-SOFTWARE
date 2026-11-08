import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import type { Row } from "../lib/api/client";
import { Badge, toneFor } from "./ui";

export interface Column {
  key: string;
  label: string;
}

const BADGE_COLUMNS = new Set([
  "status",
  "state",
  "inauthenticRisk",
  "difficulty",
  "confidence",
  "verdict",
  "rightsStatus",
  "checks",
  "result",
  "severity",
  "syncStatus",
  "tokenStatus",
  "strength",
  "qc",
]);

const AVATAR_COLUMNS = new Set(["name", "channel"]);
const AVATAR_COLORS = ["#5b3df5", "#c81e3a", "#0f7b6c", "#b45309", "#1d4ed8"];

function Avatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  const color = AVATAR_COLORS[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_COLORS.length];
  return (
    <span className="inline-flex items-center gap-2" dir="auto">
      <span
        aria-hidden="true"
        className="grid size-7 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white"
        style={{ background: color }}
      >
        {initials}
      </span>
      {name}
    </span>
  );
}

function Cell({ column, value }: { column: string; value: Row[string] }) {
  if (typeof value === "boolean")
    return <Badge tone={value ? "ok" : "neutral"}>{value ? "Yes" : "No"}</Badge>;
  if (value === null || value === undefined) return <span className="text-muted">—</span>;
  const text = typeof value === "number" ? value.toLocaleString("en-US") : value;
  if (BADGE_COLUMNS.has(column) && text !== "—") return <Badge tone={toneFor(text, column)}>{text}</Badge>;
  if (AVATAR_COLUMNS.has(column) && typeof value === "string") return <Avatar name={value} />;
  return <span dir="auto">{text}</span>;
}

const helper = createColumnHelper<Row>();

/** Sortable table (TanStack Table). Server-side sort/filter/cursor paging arrives with Phase 3 data. */
export function DataTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: readonly Column[];
  rows: Row[];
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const defs = useMemo(
    () =>
      columns.map((c) =>
        helper.accessor((r) => r[c.key] ?? null, {
          id: c.key,
          header: c.label,
          cell: (info) => <Cell column={c.key} value={info.getValue()} />,
          sortingFn: "alphanumeric",
          sortDescFirst: false,
        }),
      ),
    [columns],
  );
  const table = useReactTable({
    data: rows,
    columns: defs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="tf-card tf-rise overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-surface-2 text-xs tracking-wide text-muted uppercase">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                    className="px-4 py-2.5 text-start font-semibold whitespace-nowrap"
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-1"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <span aria-hidden="true" className="text-muted">
                        {sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : "↕"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-t border-line transition-colors hover:bg-surface-2/60">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-2.5 align-middle">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
