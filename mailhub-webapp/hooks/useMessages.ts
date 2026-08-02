"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, messageResponseSchema } from "@/lib/api";
import type { CategoryFilter } from "@/types";

type MessageResponse = z.infer<typeof messageResponseSchema>;

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: api.accounts,
    staleTime: 30_000,
  });
}

export function useMessages(accountId: number | null, category: CategoryFilter) {
  return useQuery({
    queryKey: ["messages", accountId, category],
    queryFn: () => {
      if (accountId === null) throw new Error("No account selected");
      return api.messages(accountId, category);
    },
    enabled: accountId !== null,
  });
}

export function useMessage(id: number) {
  return useQuery({
    queryKey: ["message", id],
    queryFn: () => api.message(id),
    enabled: Boolean(id),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
    staleTime: 30_000,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.markRead,
    // Optimistic update: flip is_read instantly, revert on error.
    onMutate: async (messageId: number) => {
      await qc.cancelQueries({ queryKey: ["message", messageId] });
      const previous = qc.getQueryData<MessageResponse>(["message", messageId]);
      qc.setQueryData<MessageResponse>(["message", messageId], (old) =>
        old ? { ...old, message: { ...old.message, is_read: true } } : old,
      );
      return { previous };
    },
    onError: (_err, messageId, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData<MessageResponse>(["message", messageId], ctx.previous);
      }
    },
    onSettled: (_data, _err, messageId) => {
      qc.invalidateQueries({ queryKey: ["messages"] });
      qc.invalidateQueries({ queryKey: ["message", messageId] });
    },
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteAccount,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["messages"] });
    },
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.updateSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}
