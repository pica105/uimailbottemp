/**
 * Telegram WebApp SDK helpers.
 *
 * The SDK is injected by the Telegram client; in a plain browser (dev /
 * preview) `window.Telegram` is absent, so every access is guarded and we
 * fall back to a warm light theme so the UI still looks right.
 */

export interface TelegramThemeParams {
  bg_color?: string;
  secondary_bg_color?: string;
  text_color?: string;
  hint_color?: string;
  button_color?: string;
  button_text_color?: string;
  link_color?: string;
}

interface TelegramWebAppLike {
  ready?: () => void;
  expand?: () => void;
  initData?: string;
  colorScheme?: "light" | "dark";
  themeParams?: TelegramThemeParams;
  BackButton?: {
    show?: () => void;
    hide?: () => void;
    onClick?: (cb: () => void) => void;
    offClick?: (cb: () => void) => void;
  };
  HapticFeedback?: {
    impactOccurred?: (style: string) => void;
    notificationOccurred?: (type: string) => void;
  };
  onEvent?: (event: string, cb: () => void) => void;
  offEvent?: (event: string, cb: () => void) => void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebAppLike };
  }
}

export function getWebApp(): TelegramWebAppLike | undefined {
  return window.Telegram?.WebApp;
}

export function isTelegram(): boolean {
  return Boolean(getWebApp() && getWebApp()!.initData);
}

export function getInitData(): string {
  return getWebApp()?.initData ?? "";
}

export function getThemeParams(): TelegramThemeParams {
  return getWebApp()?.themeParams ?? {};
}

export function ready() {
  try {
    getWebApp()?.ready?.();
    getWebApp()?.expand?.();
  } catch {
    /* not in Telegram */
  }
}

/**
 * Apply Telegram theme params as CSS variables on <html> and toggle the
 * `.dark` class so semantic tokens (see globals.css) pick them up.
 * Outside Telegram we follow the OS color scheme.
 */
export function applyTheme() {
  const params = getThemeParams();
  const root = document.documentElement;
  const set = (name: string, value?: string) => {
    if (value) root.style.setProperty(name, value);
  };
  set("--tg-bg", params.bg_color);
  set("--tg-secondary-bg", params.secondary_bg_color);
  set("--tg-text", params.text_color);
  set("--tg-hint", params.hint_color);
  set("--tg-button", params.button_color);
  set("--tg-button-text", params.button_text_color);
  set("--tg-link", params.link_color);

  const webApp = getWebApp();
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const isDark =
    webApp?.colorScheme === "dark" || (!webApp && prefersDark);
  root.classList.toggle("dark", isDark);
}

/** Register a callback that fires on theme changes. Returns unsubscribe. */
export function onThemeChanged(cb: () => void): () => void {
  const webApp = getWebApp();
  if (!webApp) return () => {};
  webApp.onEvent?.("themeChanged", cb);
  return () => webApp.offEvent?.("themeChanged", cb);
}

/** Light haptic feedback, silently ignored outside Telegram. */
export function hapticImpact(style: "light" | "medium" | "heavy" = "light") {
  try {
    getWebApp()?.HapticFeedback?.impactOccurred?.(style);
  } catch {
    /* noop */
  }
}

/** Show or hide the Telegram BackButton with a route-aware handler. */
export function setupBackButton(onBack: () => void): () => void {
  const webApp = getWebApp();
  if (!webApp?.BackButton) return () => {};
  webApp.BackButton.show?.();
  webApp.BackButton.onClick?.(onBack);
  return () => {
    webApp.BackButton?.offClick?.(onBack);
    webApp.BackButton?.hide?.();
  };
}
