import { useQuery } from "@tanstack/react-query";
import {
  api,
  call,
  ProblemError,
  stubApi,
  type Controls,
  type Me,
  type NotificationSummary,
  type ProjectQuota,
  type Shell,
} from "./api/client";

/** Signed-in user (GET /api/v1/auth/me). `null` = not signed in. */
export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await call(() => api.GET("/api/v1/auth/me"));
      } catch (e) {
        if (e instanceof ProblemError && e.problem.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

/** Emergency Stop, publishing kill switch and kill switches (real; live via SSE). */
export function useControls() {
  return useQuery<Controls>({
    queryKey: ["controls"],
    queryFn: () => call(() => api.GET("/api/v1/system/controls")),
  });
}

/** All channels (real since Phase 4). */
export function useChannels() {
  return useQuery({
    queryKey: ["channels"],
    queryFn: () => call(() => api.GET("/api/v1/channels", { params: { query: { limit: 100 } } })),
  });
}

/** The bell: unread and critical counts (real since Phase 4). */
export function useNotificationSummary() {
  return useQuery<NotificationSummary>({
    queryKey: ["notifications", "summary"],
    queryFn: () => call(() => api.GET("/api/v1/notifications/summary")),
    refetchInterval: 30_000,
  });
}

/** YouTube quota per Cloud project (real since Phase 4). */
export function useQuota() {
  return useQuery<ProjectQuota[]>({
    queryKey: ["quota"],
    queryFn: () => call(() => api.GET("/api/v1/quota")),
    refetchInterval: 60_000,
  });
}

/** Still-mocked top bar extra: the free-tier provider peak (AI providers arrive in Phase 5). */
export function useShell() {
  return useQuery<Shell>({ queryKey: ["shell"], queryFn: () => call(() => stubApi.GET("/shell")) });
}
