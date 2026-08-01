"use client";

import { Clock } from "lucide-react";
import { useT } from "@/lib/i18n";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

interface Props {
  value: number; // seconds
  onChange: (seconds: number) => void;
}

const PRESETS: { seconds: number; label: string }[] = [
  { seconds: 60, label: "1" },
  { seconds: 180, label: "3" },
  { seconds: 300, label: "5" },
  { seconds: 600, label: "10" },
  { seconds: 900, label: "15" },
  { seconds: 1800, label: "30" },
];

export function PollingInterval({ value, onChange }: Props) {
  const { t } = useT();

  const current = PRESETS.some((p) => p.seconds === value)
    ? String(value / 60)
    : String(Math.round(value / 60));

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-primary" />
        <div>
          <Label>{t("settings.polling")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.polling_hint")}</p>
        </div>
      </div>
      <Select value={current} onValueChange={(v) => onChange(Number(v) * 60)}>
        <SelectTrigger className="w-32" aria-label={t("settings.polling")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PRESETS.map((p) => (
            <SelectItem key={p.seconds} value={String(p.seconds / 60)}>
              {p.label} {t("settings.minutes")}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
