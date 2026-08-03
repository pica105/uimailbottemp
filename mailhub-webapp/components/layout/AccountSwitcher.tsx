"use client";

import { useEffect, useMemo } from "react";
import { ChevronDown, Mail, Plus } from "lucide-react";
import { useAccounts } from "@/hooks/useMessages";
import { useAppStore } from "@/stores/appStore";
import { useT } from "@/lib/i18n";
import { avatarColor, initials } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";

export function AccountSwitcher() {
  const { t } = useT();
  const { data, isLoading } = useAccounts();
  const activeAccountId = useAppStore((s) => s.activeAccountId);
  const setActiveAccount = useAppStore((s) => s.setActiveAccount);

  const accounts = data?.accounts ?? [];
  const active =
    accounts.find((a) => a.id === activeAccountId) ?? accounts[0] ?? null;

  // Keep the store in sync when accounts load for the first time.
  useEffect(() => {
    if (accounts.length === 0) {
      if (activeAccountId !== null) setActiveAccount(null);
      return;
    }
    if (!accounts.some((account) => account.id === activeAccountId)) {
      setActiveAccount(accounts[0].id);
    }
  }, [accounts, activeAccountId, setActiveAccount]);

  const activeLabel = useMemo(() => {
    if (isLoading) return <Skeleton className="h-8 w-28" />;
    if (!active) return <span className="text-sm text-muted-foreground">—</span>;
    return (
      <span className="flex items-center gap-2">
        <Avatar className="h-7 w-7 rounded-lg">
          <AvatarFallback className={avatarColor(active.email) + " text-[10px]"}>
            {initials(active.email)}
          </AvatarFallback>
        </Avatar>
        <span className="max-w-[120px] truncate text-sm font-medium">
          {active.email}
        </span>
      </span>
    );
  }, [isLoading, active]);

  if (isLoading) return activeLabel;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-1 rounded-xl border border-border bg-card px-2.5 py-1.5 shadow-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        aria-label={t("account.switch")}
      >
        {activeLabel}
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>{t("account.switch")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {accounts.length === 0 && (
          <div className="px-2 py-3 text-center text-sm text-muted-foreground">
            {t("empty.no_accounts")}
          </div>
        )}
        {accounts.map((acc) => (
          <DropdownMenuItem
            key={acc.id}
            onSelect={() => {
              setActiveAccount(acc.id);
            }}
            className={acc.id === active?.id ? "bg-accent/60" : undefined}
          >
            <Mail className="h-4 w-4 text-muted-foreground" />
            <span className="flex-1 truncate">{acc.email}</span>
            {acc.id === active?.id && (
              <span className="text-xs text-primary">{t("account.active")}</span>
            )}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled>
          <Plus className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">{t("empty.no_accounts_description")}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
