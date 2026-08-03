"use client";

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

  const messages = data?.pages.flatMap((page) => page.messages) ?? [];

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
