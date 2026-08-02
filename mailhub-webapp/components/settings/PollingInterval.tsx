"use client";

import { Clock } from "lucide-react";
import { useT } from "@/lib/i18n";
import { Label } from "@/components/ui/label";

/**
 * Polling interval is fully automatic (elastic 10s–5min per account).
 * The user does not choose it, so this is a static info block.
 */
export function PollingInterval() {
  const { t } = useT();

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-primary" />
        <div>
          <Label>{t("settings.polling")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.polling_hint")}</p>
        </div>
      </div>
      <span className="shrink-0 rounded-lg bg-muted/60 px-3 py-1.5 text-sm font-medium text-foreground">
        {t("settings.polling_auto")}
      </span>
    </div>
  );
}
