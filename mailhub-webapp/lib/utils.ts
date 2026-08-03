import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow } from "date-fns";
import { ru, enUS } from "date-fns/locale";
import type { Language } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Deterministic warm color for a sender avatar, derived from an email hash. */
const AVATAR_COLORS = [
  "bg-amber-500",
  "bg-orange-400",
  "bg-rose-400",
  "bg-red-400",
  "bg-amber-400",
  "bg-orange-500",
  "bg-rose-500",
  "bg-pink-500",
];

export function avatarColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

export function initials(name: string): string {
  const clean = name.trim();
  if (!clean) return "?";
  const parts = clean.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

const dateLocales = { ru, en: enUS } as const;

/**
 * Relative time: "~ 5 min ago" / "~ 5 мин назад".
 * The wordy "около"/"about" prefix is always replaced with the "~" symbol.
 */
export function formatRelativeTime(timestamp: number, lang: Language): string {
  const date = new Date(timestamp * 1000);
  const text = formatDistanceToNow(date, { addSuffix: true, locale: dateLocales[lang] });
  return "~ " + text.replace(/^(около|about)\s+/i, "");
}

/** Full localized date for the message detail screen. */
export function formatFullDate(timestamp: number, lang: Language): string {
  const date = new Date(timestamp * 1000);
  return format(date, "d MMM yyyy, HH:mm", { locale: dateLocales[lang] });
}
