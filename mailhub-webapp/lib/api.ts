/**
 * Typed API client for the MailHub backend.
 *
 * Every request sends the Telegram initData in the X-Telegram-Init-Data
 * header. Responses are validated with Zod so a backend change can never
 * silently break the UI.
 */

import { z } from "zod";
import { getInitData } from "@/lib/telegram";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------
export const accountSchema = z.object({
  id: z.number(),
  provider: z.enum(["gmail", "yandex"]),
  email: z.string(),
  is_active: z.boolean(),
  sync_error_count: z.number(),
});

export const messageSchema = z.object({
  id: z.number(),
  account_id: z.number(),
  sender_name: z.string().nullable(),
  sender_email: z.string().nullable(),
  subject: z.string(),
  snippet: z.string(),
  body_text: z.string().nullable(),
  body_html: z.string().nullable(),
  category: z.string(),
  received_at: z.number(),
  is_read: z.boolean(),
});

export const settingsSchema = z.object({
  language: z.enum(["ru", "en"]),
  muted_categories: z.array(z.string()),
  categories: z.array(z.string()),
  accounts: z.array(accountSchema),
});

export const oauthStartResponseSchema = z.object({
  auth_url: z.string(),
});

export const accountsResponseSchema = z.object({
  accounts: z.array(accountSchema),
});

export const messagesResponseSchema = z.object({
  messages: z.array(messageSchema),
  has_more: z.boolean(),
});

export const messageResponseSchema = z.object({
  message: messageSchema,
});

export const settingsResponseSchema = z.object({
  settings: settingsSchema,
});

export const okResponseSchema = z.object({ ok: z.boolean() });

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const initData = getInitData();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    throw new ApiError(401, "unauthorized");
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body?.error ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  const json = await res.json();
  return schema.parse(json);
}

export const api = {
  health: () => request("/api/health", z.object({ status: z.string() })),

  accounts: () =>
    request("/api/accounts", accountsResponseSchema, { cache: "no-store" }),

  deleteAccount: (id: number) =>
    request(`/api/accounts/${id}`, okResponseSchema, { method: "DELETE" }),

  messages: (accountId: number, category?: string, limit = 20, offset = 0) => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (category && category !== "all") params.set("category", category);
    return request(`/api/accounts/${accountId}/messages?${params}`, messagesResponseSchema, {
      cache: "no-store",
    });
  },

  message: (id: number) =>
    request(`/api/messages/${id}`, messageResponseSchema, { cache: "no-store" }),

  markRead: (id: number) =>
    request(`/api/messages/${id}/read`, okResponseSchema, { method: "POST" }),

  settings: () =>
    request("/api/settings", settingsResponseSchema, { cache: "no-store" }),

  updateSettings: (body: {
    language?: "ru" | "en";
    muted_categories?: string[];
  }) =>
    request("/api/settings", settingsResponseSchema, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** Start OAuth from inside the Mini App; returns the provider auth URL. */
  oauthStart: (provider: "gmail" | "yandex") =>
    request("/api/oauth/start", oauthStartResponseSchema, {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),
};
