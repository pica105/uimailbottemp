"use client";

import { Inbox } from "lucide-react";
import { useT } from "@/lib/i18n";

/**
 * Shown when the Mini App is opened in a plain browser (no Telegram SDK):
 * the API is unreachable without initData, so instead of confusing
 * "no accounts connected" errors we explain how to open the real app.
 */
export function OutsideTelegram() {
  const { t } = useT();

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Inbox className="h-8 w-8" />
      </div>
      <h1 className="text-xl font-bold">{t("app.title")}</h1>
      <p className="text-base font-medium">{t("outside.title")}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{t("outside.description")}</p>
    </div>
  );
}
