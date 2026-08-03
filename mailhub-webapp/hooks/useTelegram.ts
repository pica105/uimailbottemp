"use client";

import { useEffect, useState } from "react";
import {
  applyTheme,
  getInitData,
  getInitDataUserId,
  isTelegram,
  onThemeChanged,
  ready,
} from "@/lib/telegram";

export interface TelegramState {
  isTelegram: boolean;
  initData: string;
  userId: number | null;
}

// The SDK is initialized once per page load; additional subscribers only
// register for theme changes (idempotent ready()/expand()/applyTheme()).
let initialized = false;

function readState(): TelegramState {
  if (typeof window === "undefined") {
    return { isTelegram: false, initData: "", userId: null };
  }
  const initData = getInitData();
  return { isTelegram: isTelegram(), initData, userId: getInitDataUserId(initData) };
}

/**
 * Initializes the Telegram WebApp (ready + expand), applies the theme as
 * CSS variables, and keeps it in sync on themeChanged.
 */
export function useTelegram(): TelegramState {
  const [state, setState] = useState<TelegramState>(readState);

  useEffect(() => {
    if (typeof window === "undefined") return;

    if (!initialized) {
      initialized = true;
      ready();
      applyTheme();
    }

    // The SDK is normally available before hydration, but Telegram Web can
    // finish loading it just after the document becomes interactive. Poll a
    // few times so protected queries never start with an empty initData.
    const refresh = () => setState(readState());
    refresh();
    const timers = [0, 50, 250, 1_000].map((delay) =>
      window.setTimeout(refresh, delay),
    );

    const unsubscribe = onThemeChanged(() => {
      applyTheme();
      refresh();
    });

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      unsubscribe();
    };
  }, []);

  return state;
}
