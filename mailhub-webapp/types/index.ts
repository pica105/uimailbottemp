export type Language = "ru" | "en";

/** Categories are free-form: built-in buckets plus custom provider labels. */
export type Category = string;
export type CategoryFilter = "all" | Category;
/** Promo/spam stay supported for legacy cache/settings rows but are hidden. */
export type MutedCategory = Category;

export type Provider = "gmail" | "yandex";

export type ThemeMode = "white" | "dark";

export interface Account {
  id: number;
  provider: Provider;
  email: string;
  is_active: boolean;
  sync_error_count: number;
}

export interface Message {
  id: number;
  account_id: number;
  sender_name: string | null;
  sender_email: string | null;
  subject: string;
  snippet: string;
  body_text: string | null;
  body_html: string | null;
  category: Category;
  received_at: number;
  is_read: boolean;
}

export interface AppSettings {
  language: Language;
  muted_categories: MutedCategory[];
  categories: Category[];
  accounts: Account[];
}

export interface AccountsResponse {
  accounts: Account[];
}

export interface MessagesResponse {
  messages: Message[];
  has_more: boolean;
}

export interface MessageResponse {
  message: Message;
}

export interface SettingsResponse {
  settings: AppSettings;
}

export interface OAuthStartResponse {
  auth_url: string;
}
