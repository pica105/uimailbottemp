"use client";

import { motion } from "motion/react";
import { useSettings } from "@/hooks/useMessages";
import { useAppStore } from "@/stores/appStore";
import { useT } from "@/lib/i18n";
import { hapticImpact } from "@/lib/telegram";
import { cn } from "@/lib/utils";
import type { CategoryFilter } from "@/types";

// Shown while settings are still loading or unavailable.
const FALLBACK_CATEGORIES = ["important", "social", "other"];

export function CategoryTabs() {
  const { t } = useT();
  const activeCategory = useAppStore((s) => s.activeCategory);
  const setActiveCategory = useAppStore((s) => s.setActiveCategory);
  // Categories include the user's custom provider labels; refreshed from
  // the backend every time settings data reloads.
  const { data } = useSettings();
  const categories = data?.settings.categories ?? FALLBACK_CATEGORIES;

  const tabs: { value: CategoryFilter; label: string }[] = [
    { value: "all", label: t("tab.all") },
    ...categories.map((cat) => ({ value: cat as CategoryFilter, label: t(`cat.${cat}`) })),
  ];

  return (
    <div className="mb-4 flex items-center gap-1 overflow-x-auto rounded-xl bg-muted/60 p-1">
      {tabs.map((tab) => {
        const isActive = activeCategory === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => {
              setActiveCategory(tab.value);
              hapticImpact("light");
            }}
            className={cn(
              "relative flex min-h-[44px] flex-1 items-center justify-center whitespace-nowrap rounded-lg px-3 text-sm font-medium transition-colors duration-200 cursor-pointer",
              isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {isActive && (
              <motion.span
                layoutId="category-pill"
                className="absolute inset-0 rounded-lg bg-card shadow-sm"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <span className={cn("relative z-10", isActive && "glow-soft")}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
