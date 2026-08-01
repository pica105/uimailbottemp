"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { Check } from "lucide-react";
import { useMessage, useMarkRead } from "@/hooks/useMessages";
import { useT } from "@/lib/i18n";
import { setupBackButton } from "@/lib/telegram";
import { avatarColor, formatFullDate, initials } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function MessageDetail({ id }: { id: number }) {
  const { t, language } = useT();
  const router = useRouter();
  const { data, isLoading, isError } = useMessage(id);
  const markRead = useMarkRead();

  // Wire Telegram BackButton to go back.
  useEffect(() => {
    const cleanup = setupBackButton(() => router.back());
    return cleanup;
  }, [router]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return <p className="py-16 text-center text-sm text-muted-foreground">{t("error.load")}</p>;
  }

  const message = data.message;
  const sender = message.sender_name || message.sender_email || "?";
  const seed = message.sender_email || sender;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-4"
    >
      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <Avatar className="h-12 w-12">
            <AvatarFallback className={avatarColor(seed)}>{initials(sender)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{sender}</p>
            {message.sender_email && (
              <p className="truncate text-sm text-muted-foreground">{message.sender_email}</p>
            )}
            <p className="text-xs text-muted-foreground tabular-nums">
              {formatFullDate(message.received_at, language)}
            </p>
          </div>
          <Badge variant={message.category} className="shrink-0">
            {t(`cat.${message.category}`)}
          </Badge>
        </CardHeader>
        <CardContent>
          <h2 className="mb-4 text-lg font-bold leading-snug">{message.subject}</h2>
          <div className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground/90">
            {message.body_text || message.snippet}
          </div>
        </CardContent>
      </Card>

      {!message.is_read && (
        <Button
          className="w-full"
          variant="default"
          size="lg"
          onClick={() => markRead.mutate(id)}
          disabled={markRead.isPending}
        >
          <Check />
          {t("message.mark_read")}
        </Button>
      )}
      {message.is_read && (
        <p className="text-center text-sm text-muted-foreground">✓ {t("message.read")}</p>
      )}
    </motion.div>
  );
}
