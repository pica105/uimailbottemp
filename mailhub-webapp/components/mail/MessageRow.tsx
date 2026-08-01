"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { useT } from "@/lib/i18n";
import { avatarColor, cn, formatRelativeTime, initials } from "@/lib/utils";
import type { Message } from "@/types";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

interface Props {
  message: Message;
  index?: number;
}

export function MessageRow({ message, index = 0 }: Props) {
  const { t, language } = useT();
  const sender = message.sender_name || message.sender_email || "?";
  const seed = message.sender_email || sender;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.4) }}
    >
      <Link
        href={`/message/${message.id}`}
        className={cn(
          "flex items-start gap-3 rounded-xl border border-border bg-card px-3 py-3 shadow-sm transition-all duration-200",
          "hover:border-primary/30 hover:shadow-md active:scale-[0.99]",
        )}
      >
        <Avatar className="mt-0.5 h-11 w-11">
          <AvatarFallback className={avatarColor(seed)}>{initials(sender)}</AvatarFallback>
        </Avatar>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span
              className={cn(
                "truncate text-base",
                message.is_read ? "font-medium" : "font-semibold",
              )}
            >
              {sender}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {formatRelativeTime(message.received_at, language)}
            </span>
          </div>

          <p
            className={cn(
              "truncate text-sm",
              message.is_read ? "text-muted-foreground" : "text-foreground font-medium",
            )}
          >
            {message.subject}
          </p>

          {message.snippet && (
            <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground/80">
              {message.snippet}
            </p>
          )}
        </div>

        <Badge variant={message.category} className="mt-1 shrink-0">
          {t(`cat.${message.category}`)}
        </Badge>
      </Link>
    </motion.div>
  );
}
