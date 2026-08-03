"use client";

import { useEffect, useRef } from "react";
import { Inbox } from "lucide-react";
import { useMessages, useAccounts } from "@/hooks/useMessages";
import { useAppStore } from "@/stores/appStore";
import { useT } from "@/lib/i18n";
import { MessageRow } from "@/components/mail/MessageRow";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

function MessageSkeletons() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 rounded-xl border border-border bg-card p-3">
          <Skeleton className="h-11 w-11 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ icon: Icon, title, description }: {
  icon: typeof Inbox;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-8 py-20 text-center">
      <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-primary/10">
        <Icon className="h-9 w-9 text-primary" />
      </div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
    </div>
  );
}

export function MessageList() {
  const { t } = useT();
  const activeAccountId = useAppStore((s) => s.activeAccountId);
  const activeCategory = useAppStore((s) => s.activeCategory);
  const setOpenMessage = useAppStore((s) => s.setOpenMessage);
  const highlightMessageId = useAppStore((s) => s.highlightMessageId);
  const setHighlightMessage = useAppStore((s) => s.setHighlightMessage);

  const { data: accountsData, isLoading: accountsLoading } = useAccounts();
  const hasAccounts = (accountsData?.accounts.length ?? 0) > 0;

  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useMessages(activeAccountId, activeCategory);

  const messages = data?.pages.flatMap((page) => page.messages) ?? [];

  // When a directly-opened message is closed, gently scroll the list to it
  // (if it is still present) and let it flash a few times. Too-old messages
  // that are no longer loaded simply don't trigger anything.
  const scrolledFor = useRef<number | null>(null);
  useEffect(() => {
    if (highlightMessageId === null || isLoading || !data) return;
    if (scrolledFor.current === highlightMessageId) return;
    if (!messages.some((m) => m.id === highlightMessageId)) {
      setHighlightMessage(null);
      return;
    }
    scrolledFor.current = highlightMessageId;
    const el = document.querySelector(`[data-message-id="${highlightMessageId}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    // Keep the flash visible for its three pulses, then clear it.
    const timer = window.setTimeout(() => setHighlightMessage(null), 4600);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightMessageId, isLoading, data]);

  if (accountsLoading) return <MessageSkeletons />;
  if (!hasAccounts) {
    return (
      <EmptyState
        icon={Inbox}
        title={t("empty.no_accounts")}
        description={t("empty.no_accounts_description")}
      />
    );
  }
  if (isLoading && !data) return <MessageSkeletons />;

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="text-sm text-muted-foreground">{t("error.load")}</p>
        <Button variant="outline" onClick={() => refetch()}>
          {t("retry")}
        </Button>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <EmptyState
        icon={Inbox}
        title={activeCategory === "all" ? t("empty.title") : t("empty.no_results")}
        description={t("empty.description")}
      />
    );
  }

  return (
    <div className="space-y-3">
      {messages.map((m, i) => (
        <MessageRow
          key={m.id}
          message={m}
          index={i}
          onOpen={(id) => setOpenMessage(id)}
        />
      ))}
      {hasNextPage && (
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? "…" : t("messages.load_more")}
        </Button>
      )}
    </div>
  );
}
