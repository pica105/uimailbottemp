import { useAppStore } from "@/stores/appStore";
import type { Language } from "@/types";

type Dict = Record<string, string>;

const en: Dict = {
  "app.title": "MailHub",
  "app.tagline": "All your mailboxes in one place",
  "nav.inbox": "Inbox",
  "nav.settings": "Settings",
  "tab.all": "All",
  "tab.important": "Important",
  "tab.promo": "Promo",
  "tab.spam": "Spam",
  "empty.title": "No messages yet",
  "empty.description": "When new mail arrives, it will show up here. Connect an account to get started.",
  "empty.no_accounts": "No accounts connected",
  "empty.no_accounts_description":
    "Open the bot and tap “Connect Account” to link Gmail or Yandex.",
  "empty.no_results": "Nothing in this category",
  "account.switch": "Accounts",
  "account.active": "Active",
  "account.sync_error": "Sync errors: {count}",
  "account.unlink": "Unlink",
  "account.unlink_confirm_title": "Disconnect account?",
  "account.unlink_confirm_description":
    "You will stop receiving notifications from {email}. Messages will be removed.",
  "account.unlink_success": "Account disconnected",
  "message.mark_read": "Mark as read",
  "message.read": "Read",
  "message.mark_read_error": "Couldn't mark as read. Try again.",
  "settings.title": "Settings",
  "settings.language": "Language",
  "settings.language_hint": "Bot and interface language",
  "settings.polling": "Polling interval",
  "settings.polling_hint": "Fully automatic: fresh mail is checked every 10s, idle mailboxes less often",
  "settings.polling_auto": "Automatic (10s–5min)",
  "outside.title": "Open MailHub in Telegram",
  "outside.description": "The Mini App works inside Telegram. Open the bot and tap the MailHub button to see your mail.",
  "settings.muted": "Muted categories",
  "settings.muted_hint": "Notifications for these categories are hidden",
  "settings.accounts": "Connected accounts",
  "settings.save": "Save",
  "settings.saved": "Saved",
  "settings.cancel": "Cancel",
  "settings.minutes": "min",
  "lang.ru": "Русский",
  "lang.en": "English",
  "cat.important": "Important",
  "cat.promo": "Promo",
  "cat.spam": "Spam",
  "cat.other": "Other",
  "error.reopen": "Session expired. Reopen from Telegram.",
  "error.load": "Couldn't load data.",
  "retry": "Try again",
  "loading.messages": "Loading mail…",
};

const ru: Dict = {
  "app.title": "MailHub",
  "app.tagline": "Вся ваша почта в одном месте",
  "nav.inbox": "Входящие",
  "nav.settings": "Настройки",
  "tab.all": "Все",
  "tab.important": "Важное",
  "tab.promo": "Реклама",
  "tab.spam": "Спам",
  "empty.title": "Пока нет писем",
  "empty.description":
    "Когда придёт новое письмо, оно появится здесь. Подключите аккаунт, чтобы начать.",
  "empty.no_accounts": "Нет подключённых аккаунтов",
  "empty.no_accounts_description":
    "Откройте бота и нажмите «Подключить аккаунт», чтобы привязать Gmail или Яндекс.",
  "empty.no_results": "В этой категории ничего нет",
  "account.switch": "Аккаунты",
  "account.active": "Активен",
  "account.sync_error": "Ошибки синхронизации: {count}",
  "account.unlink": "Отключить",
  "account.unlink_confirm_title": "Отключить аккаунт?",
  "account.unlink_confirm_description":
    "Вы перестанете получать уведомления от {email}. Письма будут удалены.",
  "account.unlink_success": "Аккаунт отключён",
  "message.mark_read": "Отметить прочитанным",
  "message.read": "Прочитано",
  "message.mark_read_error": "Не удалось отметить прочитанным. Попробуйте ещё раз.",
  "settings.title": "Настройки",
  "settings.language": "Язык",
  "settings.language_hint": "Язык бота и интерфейса",
  "settings.polling": "Интервал проверки",
  "settings.polling_hint": "Полностью автоматический: свежее письмо — каждые 10 сек, тихий ящик — реже",
  "settings.polling_auto": "Автоматически (10с–5мин)",
  "outside.title": "Откройте MailHub в Telegram",
  "outside.description": "Mini App работает внутри Telegram. Откройте бота и нажмите кнопку MailHub, чтобы увидеть свою почту.",
  "settings.muted": "Отключённые категории",
  "settings.muted_hint": "Уведомления этих категорий скрыты",
  "settings.accounts": "Подключённые аккаунты",
  "settings.save": "Сохранить",
  "settings.saved": "Сохранено",
  "settings.cancel": "Отмена",
  "settings.minutes": "мин",
  "lang.ru": "Русский",
  "lang.en": "English",
  "cat.important": "Важное",
  "cat.promo": "Реклама",
  "cat.spam": "Спам",
  "cat.other": "Другое",
  "error.reopen": "Сессия истекла. Откройте из Telegram.",
  "error.load": "Не удалось загрузить данные.",
  "retry": "Повторить",
  "loading.messages": "Загружаем почту…",
};

const dictionaries: Record<Language, Dict> = { en, ru };

export function translate(lang: Language, key: string, vars?: Record<string, string>): string {
  const dict = dictionaries[lang] ?? dictionaries.en;
  let text = dict[key] ?? en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replaceAll(`{${k}}`, v);
    }
  }
  return text;
}

/** Reactive translation hook backed by the Zustand language setting. */
export function useT() {
  const language = useAppStore((s) => s.language);
  return {
    language,
    t: (key: string, vars?: Record<string, string>) =>
      translate(language, key, vars),
  };
}
