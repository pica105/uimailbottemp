"use client";

import { ReactNode, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Inbox, Settings as SettingsIcon } from "lucide-react";
import { AccountSwitcher } from "@/components/layout/AccountSwitcher";
import { OutsideTelegram } from "@/components/OutsideTelegram";
import { useTelegram } from "@/hooks/useTelegram";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function useClientReady() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const { t } = useT();
  const pathname = usePathname();
  const { isTelegram: telegramReady } = useTelegram();
  // Detect Telegram only after hydration to avoid SSR/client mismatch.
  const clientReady = useClientReady();

  if (clientReady && !telegramReady) {
    return <OutsideTelegram />;
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col px-4 pb-24 pt-[calc(env(safe-area-inset-top)+1rem)]">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Inbox className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-bold leading-tight">{t("app.title")}</h1>
            <p className="text-xs text-muted-foreground">{t("app.tagline")}</p>
          </div>
        </div>
        <AccountSwitcher />
      </header>

      {children}

      {/* Bottom tab bar (Telegram-native feel) */}
      <nav
        className={cn(
          "fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/90 backdrop-blur-md",
          "pb-[env(safe-area-inset-bottom)]",
        )}
      >
        <div className="mx-auto flex max-w-xl items-center justify-around px-6">
          <Link
            href="/inbox"
            className={cn(
              "flex min-h-[52px] flex-col items-center justify-center gap-0.5 text-xs font-medium transition-colors",
              pathname.startsWith("/inbox") || pathname.startsWith("/message")
                ? "text-primary"
                : "text-muted-foreground",
            )}
          >
            <Inbox className="h-5 w-5" />
            {t("nav.inbox")}
          </Link>
          <Link
            href="/settings"
            className={cn(
              "flex min-h-[52px] flex-col items-center justify-center gap-0.5 text-xs font-medium transition-colors",
              pathname.startsWith("/settings") ? "text-primary" : "text-muted-foreground",
            )}
          >
            <SettingsIcon className="h-5 w-5" />
            {t("nav.settings")}
          </Link>
        </div>
      </nav>
    </div>
  );
}
