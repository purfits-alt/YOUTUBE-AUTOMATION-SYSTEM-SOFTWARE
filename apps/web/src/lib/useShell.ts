import { useQuery } from "@tanstack/react-query";
import { api, call, type Shell } from "./api/client";

export function useShell() {
  return useQuery<Shell>({ queryKey: ["shell"], queryFn: () => call(() => api.GET("/shell")) });
}
