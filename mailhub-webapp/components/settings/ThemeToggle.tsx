"use client";

import { useEffect } from "react";
import { motion } from "motion/react";
import { Moon, Sun } from "lucide-react";
import { applyTheme, hapticImpact } from "@/lib/telegram";
import { useT } from "@/lib/i18n";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { ThemeMode } from "@/types";
import { Label } from "@/components/ui/label";

const OPTIONS: { value: ThemeMode; labelKey: string; icon: typeof Sun }[] = [
  { value: "white", labelKey: "theme.white", icon: Sun },
  { value: "dark", labelKey: "theme.dark", icon: Moon },
];

/**
 * Theme switcher styled exactly like the category tabs: a sliding pill
 * that moves left/right. Applies immediately (no Save needed).
 */
export function ThemeToggle() {
  const { t } = useT();
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Sun className="glow-icon h-4 w-4 text-primary" />
        <div>
          <Label className="glow-soft">{t("settings.theme")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.theme_hint")}</p>
        </div>
      </div>
      <div className="flex items-center gap-1 rounded-xl bg-muted/70 p-1">
        {OPTIONS.map((opt) => {
          const isActive = theme === opt.value;
          const Icon = opt.icon;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                setTheme(opt.value);
                hapticImpact("light");
              }}
              className={cn(
                "relative flex min-h-[38px] min-w-[84px] cursor-pointer items-center justify-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-colors duration-200",
                isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={isActive}
            >
              {isActive && (
                <motion.span
                  layoutId="theme-pill"
                  className="absolute inset-0 rounded-lg bg-card shadow-sm"
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <Icon
                  className={cn(
                    "h-4 w-4",
                    isActive && "glow-icon text-primary",
                  )}
                />
                {t(opt.labelKey)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
