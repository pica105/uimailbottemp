"use client";

import { Languages } from "lucide-react";
import { useAppStore } from "@/stores/appStore";
import { useT } from "@/lib/i18n";
import type { Language } from "@/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

interface Props {
  value: Language;
  onChange: (lang: Language) => void;
}

export function LanguageSelector({ value, onChange }: Props) {
  const { t } = useT();
  const setLanguage = useAppStore((s) => s.setLanguage);

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Languages className="glow-icon h-4 w-4 text-primary" />
        <div>
          <Label className="glow-soft">{t("settings.language")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.language_hint")}</p>
        </div>
      </div>
      <Select
        value={value}
        onValueChange={(v) => {
          const lang = v as Language;
          onChange(lang); // persists to backend
          setLanguage(lang); // immediate UI effect
        }}
      >
        <SelectTrigger className="w-40" aria-label={t("settings.language")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="ru">{t("lang.ru")}</SelectItem>
          <SelectItem value="en">{t("lang.en")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
