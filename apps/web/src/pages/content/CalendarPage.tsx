import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ProblemDisplay } from "../../components/ProblemDisplay";
import { StateCard } from "../../components/StateCard";
import { useToast } from "../../components/Toasts";
import { Button, Card } from "../../components/ui";
import { t } from "../../i18n";
import { api, call, type CalendarItemOut } from "../../lib/api/client";
import { useSelectedChannel } from "../../lib/channel";
import { problemText } from "../channels/common";
import { asProblem, LoadingSkeleton, PageTitle } from "../PageView";
import { getPage } from "../registry";
import { IdeaStateBadge } from "./common";

function iso(d: Date): string {
  return `${String(d.getFullYear())}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Days shown for a month: Monday-first weeks from the week of the 1st to the week of the last day. */
export function monthDays(year: number, month: number): Date[] {
  const start = new Date(year, month, 1);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const end = new Date(year, month + 1, 0);
  end.setDate(end.getDate() + ((7 - end.getDay()) % 7));
  const days: Date[] = [];
  for (const d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) days.push(new Date(d));
  return days;
}

function ItemChip({ item, onMove }: { item: CalendarItemOut; onMove: (id: string, date: string) => void }) {
  const href = item.project_id ? `/projects/${item.project_id}/script` : `/channels/${item.channel_id}/ideas`;
  return (
    <li
      draggable
      onDragStart={(e) => e.dataTransfer.setData("text/plain", item.id)}
      className="rounded-lg border border-line bg-surface-2 p-1.5 text-xs"
      data-testid={`cal-item-${item.id}`}
    >
      <Link className="block font-medium text-accent underline" to={href} dir="auto">
        {item.title}
      </Link>
      <span className="mt-1 flex flex-wrap items-center gap-1">
        <IdeaStateBadge state={item.state} />
        <span className="text-muted">{t(`content.format.${item.format}`)}</span>
      </span>
      <label className="mt-1 flex items-center gap-1 text-muted">
        <span className="sr-only">{t("calendarPage.moveLabel", { title: item.title })}</span>
        <input
          type="date"
          className="w-full rounded border border-line bg-bg px-1 text-xs"
          value={item.date}
          onChange={(e) => e.target.value && onMove(item.id, e.target.value)}
        />
      </label>
    </li>
  );
}

/** Page 10 — Content Calendar (Phase 7): scheduled ideas and their projects, for one or all channels. */
export function CalendarPage() {
  const page = getPage("calendar");
  const toast = useToast();
  const qc = useQueryClient();
  const { channelId } = useSelectedChannel();
  const navigate = useNavigate();
  const today = new Date();
  const [month, setMonth] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [allChannels, setAllChannels] = useState(true);
  const days = monthDays(month.y, month.m);
  const from = iso(days[0] ?? today);
  const to = iso(days[days.length - 1] ?? today);
  const scope = allChannels ? undefined : channelId;
  const cal = useQuery({
    queryKey: ["calendar", from, to, scope ?? "all"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/calendar", {
          params: { query: { from, to, ...(scope ? { channel_id: scope } : {}) } },
        }),
      ),
  });
  const items = cal.data?.items ?? [];
  const byDay = new Map<string, CalendarItemOut[]>();
  for (const it of items) byDay.set(it.date, [...(byDay.get(it.date) ?? []), it]);
  const move = async (id: string, date: string) => {
    try {
      await call(() =>
        api.PATCH("/api/v1/calendar/items/{idea_id}", { params: { path: { idea_id: id } }, body: { date } }),
      );
      toast(t("calendarPage.moved", { date }));
      void qc.invalidateQueries({ queryKey: ["calendar"] });
    } catch (e) {
      toast(problemText(e), "danger");
    }
  };
  const onDrop = (e: DragEvent<HTMLElement>, date: string) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain");
    if (id) void move(id, date);
  };
  const shift = (delta: number) => {
    const d = new Date(month.y, month.m + delta, 1);
    setMonth({ y: d.getFullYear(), m: d.getMonth() });
  };
  const label = new Date(month.y, month.m, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
  const weekdays = days.slice(0, 7).map((d) => d.toLocaleDateString(undefined, { weekday: "short" }));
  return (
    <div className="space-y-4" data-testid="page-calendar">
      <PageTitle page={page}>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => shift(-1)} aria-label={t("calendarPage.prev")}>
            ‹
          </Button>
          <span className="min-w-36 text-center font-semibold" aria-live="polite">
            {label}
          </span>
          <Button onClick={() => shift(1)} aria-label={t("calendarPage.next")}>
            ›
          </Button>
          <Button
            variant={allChannels ? "primary" : "secondary"}
            aria-pressed={allChannels}
            onClick={() => setAllChannels(!allChannels)}
            disabled={!channelId}
          >
            {t("calendarPage.allChannels")}
          </Button>
        </div>
      </PageTitle>
      {cal.isPending && <LoadingSkeleton />}
      {cal.isError && <ProblemDisplay problem={asProblem(cal.error)} onRetry={() => void cal.refetch()} />}
      {cal.data && items.length === 0 && (
        <StateCard
          message={t("pages.calendar.empty")}
          actionLabel={t("pages.calendar.emptyAction")}
          onAction={() => {
            if (channelId) void navigate(`/channels/${channelId}/ideas`);
          }}
        />
      )}
      {items.length > 0 && (
        <Card>
          <div data-testid="state-success" className="overflow-x-auto">
            <table className="w-full min-w-[42rem] table-fixed border-collapse text-sm">
              <caption className="sr-only">{t("calendarPage.caption", { month: label })}</caption>
              <thead>
                <tr>
                  {weekdays.map((w) => (
                    <th key={w} scope="col" className="pb-2 text-left text-xs font-medium text-muted">
                      {w}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: days.length / 7 }, (_, week) => (
                  <tr key={week}>
                    {days.slice(week * 7, week * 7 + 7).map((d) => {
                      const key = iso(d);
                      const inMonth = d.getMonth() === month.m;
                      return (
                        <td
                          key={key}
                          onDragOver={(e) => e.preventDefault()}
                          onDrop={(e) => onDrop(e, key)}
                          className={`h-28 border border-line p-1 align-top ${inMonth ? "" : "bg-surface-2/50 text-muted"}`}
                          data-testid={`day-${key}`}
                        >
                          <span className={`text-xs ${key === iso(today) ? "font-bold text-accent" : ""}`}>
                            {d.getDate()}
                          </span>
                          <ul className="mt-1 space-y-1">
                            {(byDay.get(key) ?? []).map((item) => (
                              <ItemChip
                                key={item.id}
                                item={item}
                                onMove={(id, date) => void move(id, date)}
                              />
                            ))}
                          </ul>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted">{t("calendarPage.dragHint")}</p>
        </Card>
      )}
    </div>
  );
}
