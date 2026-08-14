"use client";

import { keepPreviousData, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { applyDarkMode } from "@/lib/dark-mode";
import { restoreQueryCache, subscribeQueryCachePersist } from "@/lib/query-cache";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => {
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 5 * 60_000,
          gcTime: 30 * 60_000,
          retry: 1,
          refetchOnWindowFocus: false,
          refetchOnMount: false,
          placeholderData: keepPreviousData,
        },
      },
    });
    restoreQueryCache(qc);
    return qc;
  });

  useEffect(() => {
    applyDarkMode(true);
    return subscribeQueryCachePersist(client);
  }, [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
