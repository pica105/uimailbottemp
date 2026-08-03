"use client";

import { BellOff } from "lucide-react";
import { useT } from "@/lib/i18n";
import type { MutedCategory } from "@/types";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

interface Props {
  value: MutedCategory[];
  categories: string[];
  onChange: (categories: MutedCategory[]) => void;
}

export function MutedCategories({ value, categories, onChange }: Props) {
  const { t } = useT();

  const toggle = (category: string, checked: boolean) => {
    if (checked) {
      onChange([...value, category]);
    } else {
      onChange(value.filter((c) => c !== category));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <BellOff className="glow-icon h-4 w-4 text-primary" />
        <div>
          <Label className="glow-soft">{t("settings.muted")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.muted_hint")}</p>
        </div>
      </div>
      <div className="space-y-2 rounded-xl border border-border bg-muted/30 p-3">
        {categories.map((cat) => (
          <div
            key={cat}
            className="flex items-center justify-between rounded-lg px-2 py-1.5"
          >
            <Label className="cursor-pointer">{t(`cat.${cat}`)}</Label>
            <Switch
              checked={value.includes(cat)}
              onCheckedChange={(checked) => toggle(cat, checked)}
              aria-label={t(`cat.${cat}`)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
