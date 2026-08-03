"use client";

import { useState } from "react";
import { Mail, Trash2 } from "lucide-react";
import { useDeleteAccount } from "@/hooks/useMessages";
import { useT } from "@/lib/i18n";
import { avatarColor, initials } from "@/lib/utils";
import type { Account } from "@/types";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
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

interface Props {
  accounts: Account[];
}

export function AccountsList({ accounts }: Props) {
  const { t } = useT();
  const deleteAccount = useDeleteAccount();
  const [pending, setPending] = useState<Account | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Mail className="h-4 w-4 text-primary" />
        <Label>{t("settings.accounts")}</Label>
      </div>

      {accounts.length === 0 && (
        <p className="rounded-xl border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
          {t("empty.no_accounts_description")}
        </p>
      )}

      <div className="space-y-2">
        {accounts.map((acc) => (
          <div
            key={acc.id}
            className="flex items-center gap-3 rounded-xl border border-border bg-card p-3 shadow-sm"
          >
            <Avatar className="h-9 w-9 rounded-lg">
              <AvatarFallback className={avatarColor(acc.email) + " text-[10px]"}>
                {initials(acc.email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{acc.email}</p>
              <p className="text-xs capitalize text-muted-foreground">{acc.provider}</p>
            </div>
            {!acc.is_active && (
              <Badge variant="spam">{t("account.sync_error", { count: String(acc.sync_error_count) })}</Badge>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => setPending(acc)}
              aria-label={t("account.unlink")}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
      </div>

      {deleteAccount.isError && (
        <p className="text-sm text-destructive" role="alert">
          {t("error.delete_account")}
        </p>
      )}

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("account.unlink_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("account.unlink_confirm_description", { email: pending?.email ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("settings.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                if (pending) {
                  deleteAccount.mutate(pending.id, {
                    onSettled: () => setPending(null),
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
    </div>
  );
}
