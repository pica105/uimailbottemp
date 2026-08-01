import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CategoryFilter, Language } from "@/types";

interface AppState {
  language: Language;
  activeAccountId: number | null;
  activeCategory: CategoryFilter;
  setLanguage: (lang: Language) => void;
  setActiveAccount: (id: number | null) => void;
  setActiveCategory: (cat: CategoryFilter) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      language: "en",
      activeAccountId: null,
      activeCategory: "all",
      setLanguage: (language) => set({ language }),
      setActiveAccount: (activeAccountId) => set({ activeAccountId }),
      setActiveCategory: (activeCategory) => set({ activeCategory }),
    }),
    {
      name: "mailhub-app",
      partialize: (s) => ({
        language: s.language,
        activeAccountId: s.activeAccountId,
        activeCategory: s.activeCategory,
      }),
    },
  ),
);
