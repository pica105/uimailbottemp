"use client";

import { ReactNode, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTelegram } from "@/hooks/useTelegram";

export function Providers({ children }: { children: ReactNode }) {
  // Initializes the Telegram WebApp, applies the theme, subscribes to
  // themeChanged, and stays in sync with the client color scheme.
  useTelegram();

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
