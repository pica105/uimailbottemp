import { useAppStore } from "@/stores/appStore";
import type { Language } from "@/types";

type Dict = Record<string, string>;

const en: Dict = {
  "app.title": "MailHub",
  "app.tagline": "All your mailboxes in one place",
  "nav.inbox": "Inbox",
  "nav.settings": "Settings",
  "tab.all": "All",
  "empty.title": "No messages yet",
  "empty.description": "When new mail arrives, it will show up here. Connect an account to get started.",
  "empty.no_accounts": "No accounts connected",
  "empty.no_accounts_description":
    "Open the bot and tap “Connect” to link Gmail or Yandex.",
  "empty.no_results": "Nothing in this category",
  "account.switch": "Accounts",
  "account.connect": "Connect account",
  "account.connect_gmail": "Connect Gmail",
  "account.connect_yandex": "Connect Yandex",
  "account.connect_open": "Opening authorization…",
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
  "settings.theme": "Theme",
  "settings.theme_hint": "White or dark interface",
  "settings.language": "Language",
  "settings.language_hint": "Bot and interface language",
  "settings.muted": "Muted categories",
  "settings.muted_hint": "Notifications for these categories are hidden",
  "settings.save": "Save",
  "settings.saved": "Saved",
  "settings.save_hint": "Make changes to enable",
  "settings.cancel": "Cancel",
  "lang.ru": "Русский",
  "lang.en": "English",
  "theme.white": "White",
  "theme.dark": "Dark",
  "cat.important": "Important",
  "cat.promo": "Promo",
  "cat.spam": "Spam",
  "cat.social": "Social",
  "cat.other": "Other",
  "error.reopen": "Session expired. Reopen from Telegram.",
  "error.load": "Couldn't load data.",
  "error.delete_account": "Couldn't disconnect this account. Try again.",
  "retry": "Try again",
  "loading.messages": "Loading mail…",
  "messages.load_more": "Load more",
};

const ru: Dict = {
  "app.title": "MailHub",
  "app.tagline": "Вся ваша почта в одном месте",
  "nav.inbox": "Входящие",
  "nav.settings": "Настройки",
  "tab.all": "Все",
  "empty.title": "Пока нет писем",
  "empty.description":
    "Когда придёт новое письмо, оно появится здесь. Подключите аккаунт, чтобы начать.",
  "empty.no_accounts": "Нет подключённых аккаунтов",
  "empty.no_accounts_description":
    "Откройте бота и нажмите «Подключить», чтобы привязать Gmail или Яндекс.",
  "empty.no_results": "В этой категории ничего нет",
  "account.switch": "Аккаунты",
  "account.connect": "Подключить аккаунт",
  "account.connect_gmail": "Подключить Gmail",
  "account.connect_yandex": "Подключить Яндекс",
  "account.connect_open": "Открываем авторизацию…",
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
  "settings.theme": "Тема",
  "settings.theme_hint": "Белая или тёмная тема",
  "settings.language": "Язык",
  "settings.language_hint": "Язык бота и интерфейса",
  "settings.muted": "Отключённые категории",
  "settings.muted_hint": "Уведомления этих категорий скрыты",
  "settings.save": "Сохранить",
  "settings.saved": "Сохранено",
  "settings.save_hint": "Внесите изменения, чтобы сохранить",
  "settings.cancel": "Отмена",
  "lang.ru": "Русский",
  "lang.en": "English",
  "theme.white": "Белая",
  "theme.dark": "Тёмная",
  "cat.important": "Важное",
  "cat.promo": "Реклама",
  "cat.spam": "Спам",
  "cat.social": "Соцсети",
  "cat.other": "Другое",
  "error.reopen": "Сессия истекла. Откройте из Telegram.",
  "error.load": "Не удалось загрузить данные.",
  "error.delete_account": "Не удалось отключить аккаунт. Попробуйте ещё раз.",
  "retry": "Повторить",
  "loading.messages": "Загружаем почту…",
  "messages.load_more": "Загрузить ещё",
};

const dictionaries: Record<Language, Dict> = { en, ru };

export function translate(lang: Language, key: string, vars?: Record<string, string>): string {
  const dict = dictionaries[lang] ?? dictionaries.en;
  let text = dict[key] ?? en[key];
  if (text === undefined) {
    // Custom provider labels render their raw name instead of a missing key.
    text = key.startsWith("cat.") ? key.slice(4) : key;
  }
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
