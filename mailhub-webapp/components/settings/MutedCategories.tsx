"use client";

import { BellOff } from "lucide-react";
import { useT } from "@/lib/i18n";
import type { MutedCategory } from "@/types";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

interface Props {
  value: MutedCategory[];
  onChange: (categories: MutedCategory[]) => void;
}

const OPTIONS: { category: MutedCategory; labelKey: string }[] = [
  { category: "promo", labelKey: "cat.promo" },
  { category: "spam", labelKey: "cat.spam" },
  { category: "other", labelKey: "cat.other" },
];

export function MutedCategories({ value, onChange }: Props) {
  const { t } = useT();

  const toggle = (category: MutedCategory, checked: boolean) => {
    if (checked) {
      onChange([...value, category]);
    } else {
      onChange(value.filter((c) => c !== category));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <BellOff className="h-4 w-4 text-primary" />
        <div>
          <Label>{t("settings.muted")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.muted_hint")}</p>
        </div>
      </div>
      <div className="space-y-2 rounded-xl border border-border bg-muted/30 p-3">
        {OPTIONS.map((opt) => (
          <div
            key={opt.category}
            className="flex items-center justify-between rounded-lg px-2 py-1.5"
          >
            <Label className="cursor-pointer">{t(opt.labelKey)}</Label>
            <Switch
              checked={value.includes(opt.category)}
              onCheckedChange={(checked) => toggle(opt.category, checked)}
              aria-label={t(opt.labelKey)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
