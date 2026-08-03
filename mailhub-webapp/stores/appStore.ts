import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CategoryFilter, Language, ThemeMode } from "@/types";

interface AppState {
  language: Language;
  theme: ThemeMode;
  activeAccountId: number | null;
  activeCategory: CategoryFilter;
  /** The message currently open inside the inbox overlay, if any. */
  openMessageId: number | null;
  /** Saved window scroll per tab so navigation preserves the position. */
  scroll: { inbox: number; settings: number };
  /** Saved scroll of the open message detail panel. */
  detailScrollY: number;
  setLanguage: (lang: Language) => void;
  setTheme: (theme: ThemeMode) => void;
  setActiveAccount: (id: number | null) => void;
  setActiveCategory: (cat: CategoryFilter) => void;
  setOpenMessage: (id: number | null) => void;
  setScroll: (key: "inbox" | "settings", y: number) => void;
  setDetailScrollY: (y: number) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      language: "en",
      theme: "white",
      activeAccountId: null,
      activeCategory: "all",
      openMessageId: null,
      scroll: { inbox: 0, settings: 0 },
      detailScrollY: 0,
      setLanguage: (language) => set({ language }),
      setTheme: (theme) => set({ theme }),
      setActiveAccount: (activeAccountId) => set({ activeAccountId }),
      setActiveCategory: (activeCategory) => set({ activeCategory }),
      setOpenMessage: (openMessageId) => set({ openMessageId }),
      setScroll: (key, y) =>
        set((s) => ({ scroll: { ...s.scroll, [key]: y } })),
      setDetailScrollY: (detailScrollY) => set({ detailScrollY }),
    }),
    {
      name: "mailhub-app",
      partialize: (s) => ({
        language: s.language,
        theme: s.theme,
        activeAccountId: s.activeAccountId,
        activeCategory: s.activeCategory,
        openMessageId: s.openMessageId,
        scroll: s.scroll,
        detailScrollY: s.detailScrollY,
      }),
    },
  ),
);
