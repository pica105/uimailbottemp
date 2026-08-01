"use client";

import { useMemo } from "react";
import { useTelegram } from "@/hooks/useTelegram";

export interface TelegramUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

/** Parse the JSON user field from initData. */
export function parseInitDataUser(initData: string): TelegramUser | null {
  if (!initData) return null;
  const params = new URLSearchParams(initData);
  const userRaw = params.get("user");
  if (!userRaw) return null;
  try {
    return JSON.parse(userRaw) as TelegramUser;
  } catch {
    return null;
  }
}

/**
 * Auth state for the Mini App. The backend validates initData via HMAC,
 * so presence of initData is enough for the client to proceed.
 */
export function useAuth() {
  const { isTelegram, initData } = useTelegram();

  const user = useMemo(() => parseInitDataUser(initData), [initData]);

  return {
    isTelegram,
    initData,
    user,
    isAuthenticated: Boolean(initData),
  };
}
