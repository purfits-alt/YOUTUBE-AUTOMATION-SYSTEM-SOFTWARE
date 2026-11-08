import { useQuery } from "@tanstack/react-query";
import { api, call, ProblemError, stubApi, type Controls, type Me, type Shell } from "./api/client";

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

/** Top bar extras that are still mocked: channels (Phase 4), quota (Phase 4), unread count (Phase 14). */
export function useShell() {
  return useQuery<Shell>({ queryKey: ["shell"], queryFn: () => call(() => stubApi.GET("/shell")) });
}
