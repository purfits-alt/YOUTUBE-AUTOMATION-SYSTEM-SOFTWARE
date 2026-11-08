import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider, type createMemoryRouter } from "react-router";
import { ReauthProvider } from "../components/ReauthModal";
import { ToastProvider } from "../components/Toasts";
import { routes } from "./routes";

export function makeQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
}

type Router = ReturnType<typeof createBrowserRouter> | ReturnType<typeof createMemoryRouter>;

export function App({ router, queryClient }: { router?: Router; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? makeQueryClient());
  const [r] = useState(() => router ?? createBrowserRouter(routes));
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ReauthProvider>
          <RouterProvider router={r} />
        </ReauthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
