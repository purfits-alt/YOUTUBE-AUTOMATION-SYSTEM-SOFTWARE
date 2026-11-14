import type { QueryClient } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { API_BASE } from "./api/client";

/** Server-sent event names (BACKEND_SPECIFICATION §2). */
export type EventName =
  | "state.changed"
  | "approval.requested"
  | "notification.created"
  | "quota.updated"
  | "usage.updated"
  | "control.changed"
  | "job.progress"
  | "job.finished"
  | "channel.health";

/** Which query keys each event invalidates. */
const INVALIDATES: Record<EventName, readonly string[]> = {
  "state.changed": ["page", "overview"],
  "approval.requested": ["overview", "page"],
  "notification.created": ["shell"],
  "quota.updated": ["shell", "overview"],
  "usage.updated": ["shell", "overview"],
  "control.changed": ["controls"],
  "job.progress": ["page"],
  "job.finished": ["page"],
  "channel.health": ["shell", "page"],
};

export const EVENT_NAMES = Object.keys(INVALIDATES) as EventName[];

/** Apply one event to the TanStack Query cache. control.changed carries the full controls object. */
export function applyEvent(queryClient: QueryClient, name: EventName, data: unknown): void {
  if (name === "control.changed" && data && typeof data === "object") {
    queryClient.setQueryData(["controls"], data);
    return;
  }
  for (const key of INVALIDATES[name]) void queryClient.invalidateQueries({ queryKey: [key] });
}

/** One EventSource for the whole app (FRONTEND_SPECIFICATION §0.4). It reconnects by itself and
 * replays missed events with Last-Event-ID. */
export function useEventStream(enabled: boolean): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    // The public demo has no server to stream from (sample data only).
    if (!enabled || typeof EventSource === "undefined" || import.meta.env.VITE_DEMO === "on") return;
    const source = new EventSource(`${API_BASE}/events/stream`);
    const handlers = EVENT_NAMES.map((name) => {
      const handler = (e: MessageEvent<string>) => {
        let data: unknown;
        try {
          data = JSON.parse(e.data);
        } catch {
          data = null;
        }
        applyEvent(queryClient, name, data);
      };
      source.addEventListener(name, handler);
      return [name, handler] as const;
    });
    return () => {
      for (const [name, handler] of handlers) source.removeEventListener(name, handler);
      source.close();
    };
  }, [enabled, queryClient]);
}
