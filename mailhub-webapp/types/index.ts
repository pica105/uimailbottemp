export type Language = "ru" | "en";

export type Category = "important" | "promo" | "spam" | "other";
export type CategoryFilter = "all" | Category;
/** Categories that can be muted (important can never be muted). */
export type MutedCategory = "promo" | "spam" | "other";

export type Provider = "gmail" | "yandex";

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
  category: Category;
  received_at: number;
  is_read: boolean;
}

export interface AppSettings {
  language: Language;
  polling_interval_seconds: number;
  muted_categories: MutedCategory[];
  accounts: Account[];
}

export interface AccountsResponse {
  accounts: Account[];
}

export interface MessagesResponse {
  messages: Message[];
}

export interface MessageResponse {
  message: Message;
}

export interface SettingsResponse {
  settings: AppSettings;
}
