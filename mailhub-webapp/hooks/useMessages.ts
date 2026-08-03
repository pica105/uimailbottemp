"use client";

import {
  useMutation,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { z } from "zod";
import { api, messageResponseSchema } from "@/lib/api";
import { useTelegram } from "@/hooks/useTelegram";
import type { CategoryFilter } from "@/types";

type MessageResponse = z.infer<typeof messageResponseSchema>;

export function useAccounts() {
  const { initData, userId } = useTelegram();
  return useQuery({
    queryKey: ["accounts", userId],
    queryFn: api.accounts,
    enabled: Boolean(initData),
    staleTime: 30_000,
  });
}

export function useMessages(accountId: number | null, category: CategoryFilter) {
  const { initData, userId } = useTelegram();
  return useInfiniteQuery({
    queryKey: ["messages", userId, accountId, category],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      if (accountId === null) throw new Error("No account selected");
      return api.messages(accountId, category, 20, pageParam);
    },
    getNextPageParam: (lastPage, allPages) =>
      lastPage.has_more ? allPages.length * 20 : undefined,
    enabled: accountId !== null && Boolean(initData),
  });
}

export function useMessage(id: number) {
  const { initData, userId } = useTelegram();
  return useQuery({
    queryKey: ["message", userId, id],
    queryFn: () => api.message(id),
    enabled: Boolean(id) && Boolean(initData),
  });
}

export function useSettings() {
  const { initData, userId } = useTelegram();
  return useQuery({
    queryKey: ["settings", userId],
    queryFn: api.settings,
    enabled: Boolean(initData),
    // Always stale: reopening Settings must re-load the user's categories.
    staleTime: 0,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  const { userId } = useTelegram();
  return useMutation({
    mutationFn: api.markRead,
    // Optimistic update: flip is_read instantly, revert on error.
    onMutate: async (messageId: number) => {
      const queryKey = ["message", userId, messageId] as const;
      await qc.cancelQueries({ queryKey });
      const previous = qc.getQueryData<MessageResponse>(queryKey);
      qc.setQueryData<MessageResponse>(queryKey, (old) =>
        old ? { ...old, message: { ...old.message, is_read: true } } : old,
      );
      return { previous };
    },
    onError: (_err, messageId, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData<MessageResponse>(["message", userId, messageId], ctx.previous);
      }
    },
    onSettled: (_data, _err, messageId) => {
      qc.invalidateQueries({ queryKey: ["messages"] });
      qc.invalidateQueries({ queryKey: ["message", userId, messageId] });
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
