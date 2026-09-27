"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/** Feature-local TanStack Query client (spec: "isolated from the rest of
 * the app") -- this page owns its own cache rather than reaching into a
 * global provider that doesn't exist yet elsewhere in the app. */
export function KnowledgeGraphQueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 10_000 },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
