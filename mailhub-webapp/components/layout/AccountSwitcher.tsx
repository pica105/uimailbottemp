"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Loader2, Mail, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAccounts, useDeleteAccount } from "@/hooks/useMessages";
import { useAppStore } from "@/stores/appStore";
import { useT } from "@/lib/i18n";
import { openLink } from "@/lib/telegram";
import { avatarColor, initials } from "@/lib/utils";
import type { Account, Provider } from "@/types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";

const PROVIDERS: { provider: Provider; labelKey: string }[] = [
  { provider: "gmail", labelKey: "account.connect_gmail" },
  { provider: "yandex", labelKey: "account.connect_yandex" },
];

export function AccountSwitcher() {
  const { t } = useT();
  const { data, isLoading } = useAccounts();
  const activeAccountId = useAppStore((s) => s.activeAccountId);
  const setActiveAccount = useAppStore((s) => s.setActiveAccount);
  const deleteAccount = useDeleteAccount();

  const [connecting, setConnecting] = useState<Provider | null>(null);
  const [pendingUnlink, setPendingUnlink] = useState<Account | null>(null);

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

  const connect = async (provider: Provider) => {
    setConnecting(provider);
    try {
      const { auth_url } = await api.oauthStart(provider);
      openLink(auth_url);
    } catch {
      // Backend unreachable/401: keep the dropdown usable; the user can
      // retry or use the bot's Connect flow.
    } finally {
      setConnecting(null);
    }
  };

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
        <span className="glow-soft max-w-[120px] truncate text-sm font-medium">
          {active.email}
        </span>
      </span>
    );
  }, [isLoading, active]);

  if (isLoading) return activeLabel;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="flex items-center gap-1 rounded-xl border border-border bg-card px-2.5 py-1.5 shadow-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          aria-label={t("account.switch")}
        >
          {activeLabel}
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel>{t("account.switch")}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {accounts.length === 0 && (
            <div className="px-2 py-2 text-center text-sm text-muted-foreground">
              {t("empty.no_accounts")}
            </div>
          )}
          {accounts.map((acc) => (
            <DropdownMenuItem
              key={acc.id}
              onSelect={() => setActiveAccount(acc.id)}
              className={acc.id === active?.id ? "bg-accent/60" : undefined}
            >
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span className="glow-soft flex-1 truncate">{acc.email}</span>
              <span
                role="button"
                tabIndex={0}
                aria-label={t("account.unlink")}
                onClick={(event) => {
                  event.stopPropagation();
                  setPendingUnlink(acc);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.stopPropagation();
                    setPendingUnlink(acc);
                  }
                }}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </span>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          {PROVIDERS.map(({ provider, labelKey }) => (
            <DropdownMenuItem
              key={provider}
              disabled={connecting !== null}
              onSelect={(event) => {
                event.preventDefault();
                connect(provider);
              }}
            >
              {connecting === provider ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              ) : (
                <Plus className="h-4 w-4 text-primary" />
              )}
              <span className="text-primary">{t(labelKey)}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog
        open={pendingUnlink !== null}
        onOpenChange={(open) => !open && setPendingUnlink(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("account.unlink_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("account.unlink_confirm_description", {
                email: pendingUnlink?.email ?? "",
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("settings.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                if (pendingUnlink) {
                  deleteAccount.mutate(pendingUnlink.id, {
                    onSettled: () => setPendingUnlink(null),
                  });
                }
              }}
              disabled={deleteAccount.isPending}
            >
              {t("account.unlink")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
