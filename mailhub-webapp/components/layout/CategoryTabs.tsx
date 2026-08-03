"use client";

import { motion } from "motion/react";
import { useAppStore } from "@/stores/appStore";
import { useT } from "@/lib/i18n";
import { hapticImpact } from "@/lib/telegram";
import { cn } from "@/lib/utils";
import type { CategoryFilter } from "@/types";

const TABS: { value: CategoryFilter; labelKey: string }[] = [
  { value: "all", labelKey: "tab.all" },
  { value: "important", labelKey: "tab.important" },
  { value: "social", labelKey: "tab.social" },
  { value: "other", labelKey: "tab.other" },
];

export function CategoryTabs() {
  const { t } = useT();
  const activeCategory = useAppStore((s) => s.activeCategory);
  const setActiveCategory = useAppStore((s) => s.setActiveCategory);

  return (
    <div className="mb-4 flex items-center gap-1 overflow-x-auto rounded-xl bg-muted/60 p-1">
      {TABS.map((tab) => {
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
                className="absolute inset-0 rounded-lg bg-background shadow-sm"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <span className="relative z-10">{t(tab.labelKey)}</span>
          </button>
        );
      })}
    </div>
  );
}
