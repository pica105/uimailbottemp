"use client";

import { useEffect, useState } from "react";
import { applyTheme, getInitData, isTelegram, onThemeChanged, ready } from "@/lib/telegram";

export interface TelegramState {
  isTelegram: boolean;
  initData: string;
}

// The SDK is initialized once per page load; additional subscribers only
// register for theme changes (idempotent ready()/expand()/applyTheme()).
let initialized = false;

function readState(): TelegramState {
  if (typeof window === "undefined") {
    return { isTelegram: false, initData: "" };
  }
  return { isTelegram: isTelegram(), initData: getInitData() };
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

    const unsubscribe = onThemeChanged(() => {
      applyTheme();
      setState(readState());
    });

    return unsubscribe;
  }, []);

  return state;
}
