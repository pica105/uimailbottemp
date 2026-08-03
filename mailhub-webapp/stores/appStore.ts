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
  /**
   * Message to highlight in the inbox list (set when closing a directly
   * opened message; the list scrolls to it and flashes it a few times).
   */
  highlightMessageId: number | null;
  setLanguage: (lang: Language) => void;
  setTheme: (theme: ThemeMode) => void;
  setActiveAccount: (id: number | null) => void;
  setActiveCategory: (cat: CategoryFilter) => void;
  setOpenMessage: (id: number | null) => void;
  setScroll: (key: "inbox" | "settings", y: number) => void;
  setDetailScrollY: (y: number) => void;
  setHighlightMessage: (id: number | null) => void;
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
      highlightMessageId: null,
      setLanguage: (language) => set({ language }),
      setTheme: (theme) => set({ theme }),
      setActiveAccount: (activeAccountId) => set({ activeAccountId }),
      setActiveCategory: (activeCategory) => set({ activeCategory }),
      setOpenMessage: (openMessageId) => set({ openMessageId }),
      setScroll: (key, y) =>
        set((s) => ({ scroll: { ...s.scroll, [key]: y } })),
      setDetailScrollY: (detailScrollY) => set({ detailScrollY }),
      setHighlightMessage: (highlightMessageId) => set({ highlightMessageId }),
    }),
    {
      name: "mailhub-app",
      // highlightMessageId is intentionally session-local: a highlight set
      // when a directly-opened message is closed must not survive a Mini App
      // relaunch (it would re-scroll/re-flash an old message next session).
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
