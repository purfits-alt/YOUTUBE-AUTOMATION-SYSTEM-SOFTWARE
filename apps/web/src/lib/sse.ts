import type { QueryClient } from "@tanstack/react-query";

/** Server-sent event names from FRONTEND_SPECIFICATION (per page "Real-time events"). */
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
  "control.changed": ["shell"],
  "job.progress": ["page"],
  "job.finished": ["page"],
  "channel.health": ["shell", "page"],
};

/**
 * SSE client stub. Phase 3 opens one EventSource on /api/v1/events/stream; until then events can be
 * dispatched locally (mocks and tests) and drive the same TanStack Query invalidation.
 */
export function createEventBus(queryClient: QueryClient) {
  return {
    dispatch(name: EventName): void {
      for (const key of INVALIDATES[name]) void queryClient.invalidateQueries({ queryKey: [key] });
    },
  };
}
