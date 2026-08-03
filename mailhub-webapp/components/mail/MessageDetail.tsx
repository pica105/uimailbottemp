"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { Check, X } from "lucide-react";
import { useMessage, useMarkRead } from "@/hooks/useMessages";
import { useT } from "@/lib/i18n";
import { setupBackButton } from "@/lib/telegram";
import { avatarColor, cn, formatFullDate, initials } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { BlobButton } from "@/components/ui/blob-button";
import { EmailBody } from "@/components/mail/EmailBody";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  id: number;
  /** When set, renders as a full-screen overlay with a close button. */
  overlay?: boolean;
  /**
   * When set, renders as a standalone full-screen view (deep link from a
   * Telegram notification). Header shows the category on the left and a
   * close button on the right; closing returns to the inbox and highlights
   * the message in the list.
   */
  standalone?: boolean;
  onClose?: () => void;
}

export function MessageDetail({ id, overlay = false, standalone = false, onClose }: Props) {
  const { t, language } = useT();
  const router = useRouter();
  const { data, isLoading, isError } = useMessage(id);
  const markRead = useMarkRead();
  const scrollRef = useRef<HTMLDivElement>(null);
  const setDetailScrollY = useAppStore((s) => s.setDetailScrollY);
  const setHighlightMessage = useAppStore((s) => s.setHighlightMessage);

  const message = data?.message;

  const isFullscreen = overlay || standalone;

  const handleClose = useCallback(() => {
    // Persist the detail scroll so re-opening (or returning from Settings)
    // lands exactly where the user left off.
    if (scrollRef.current) {
      setDetailScrollY(scrollRef.current.scrollTop);
    }
    if (standalone) {
      setHighlightMessage(id);
      router.replace("/inbox");
      return;
    }
    onClose?.();
  }, [id, onClose, router, setDetailScrollY, setHighlightMessage, standalone]);

  // Wire Telegram BackButton: fullscreen views close, standalone goes back
  // to the inbox with the message highlighted.
  useEffect(() => {
    if (!isFullscreen) return;
    const cleanup = setupBackButton(handleClose);
    return cleanup;
  }, [isFullscreen, handleClose]);

  // Restore the saved detail scroll once the content is loaded — exactly
  // once per message. Without this guard the optimistic is_read flip (and
  // the refetch after it) would re-trigger the restore and snap the panel
  // back to the top while the user is reading.
  const restoredFor = useRef<number | null>(null);
  useEffect(() => {
    if (!message || !isFullscreen || !scrollRef.current) return;
    if (restoredFor.current === message.id) return;
    restoredFor.current = message.id;
    scrollRef.current.scrollTop = useAppStore.getState().detailScrollY;
  }, [isFullscreen, message]);

  // Auto mark-as-read when the user scrolls to the end of the message.
  useEffect(() => {
    if (!message || message.is_read || markRead.isPending) return;
    const check = () => {
      if (message.is_read || markRead.isPending) return;
      const atEnd = isFullscreen
        ? scrollRef.current &&
          scrollRef.current.scrollHeight - scrollRef.current.scrollTop -
            scrollRef.current.clientHeight <
            64
        : window.innerHeight + window.scrollY >=
          document.documentElement.scrollHeight - 64;
      if (atEnd) {
        markRead.mutate(id);
      }
    };
    // A short delay lets the layout settle before the first check.
    const timer = window.setTimeout(check, 400);
    const target = isFullscreen ? scrollRef.current : window;
    target?.addEventListener("scroll", check, { passive: true });
    return () => {
      window.clearTimeout(timer);
      target?.removeEventListener("scroll", check);
    };
  }, [isFullscreen, message, id, markRead, markRead.isPending]);

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !message) {
    return (
      <p className="py-16 text-center text-sm text-muted-foreground">
        {t("error.load")}
      </p>
    );
  }

  const sender = message.sender_name || message.sender_email || "?";
  const seed = message.sender_email || sender;

  const content = (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <Avatar className="h-12 w-12">
            <AvatarFallback className={avatarColor(seed)}>
              {initials(sender)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{sender}</p>
            {message.sender_email && (
              <p className="truncate text-sm text-muted-foreground">
                {message.sender_email}
              </p>
            )}
            <p className="text-xs text-muted-foreground tabular-nums">
              {formatFullDate(message.received_at, language)}
            </p>
          </div>
          <Badge
            variant={message.category as never}
            className={cn("shrink-0", message.is_read && "opacity-40")}
          >
            {t(`cat.${message.category}`)}
          </Badge>
        </CardHeader>
        <CardContent>
          <h2 className="mb-4 text-lg font-bold leading-snug">
            {message.subject}
          </h2>
          <EmailBody
            html={message.body_html ?? ""}
            fallbackText={message.body_text || message.snippet}
          />
        </CardContent>
      </Card>

      {markRead.isError && (
        <p className="py-2 text-center text-sm text-destructive">
          {t("message.mark_read_error")}
        </p>
      )}
      {!message.is_read && (
        <BlobButton
          className="w-full"
          variant="default"
          size="lg"
          onClick={() => markRead.mutate(id)}
          disabled={markRead.isPending}
        >
          <Check />
          {t("message.mark_read")}
        </BlobButton>
      )}
      {message.is_read && !markRead.isError && (
        <p className="text-center text-sm text-muted-foreground">
          ✓ {t("message.read")}
        </p>
      )}
    </div>
  );

  // Both call sites (inbox overlay and the deep-link page) render fullscreen;
  // the overlay container is the only presentation for a message detail.
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 24 }}
      transition={{ duration: 0.28, ease: "easeOut" }}
      className="fixed inset-0 z-50 flex flex-col bg-background"
    >
      <header className="flex items-center justify-between border-b border-border bg-background/90 px-4 py-3 backdrop-blur">
        {standalone ? (
          <Badge
            variant={message.category as never}
            className="glow-soft"
          >
            {t(`cat.${message.category}`)}
          </Badge>
        ) : (
          <span className="text-sm font-semibold text-muted-foreground">
            {t("nav.inbox")}
          </span>
        )}
        <button
          type="button"
          onClick={handleClose}
          className="flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
          aria-label={t("nav.inbox")}
        >
          <X className="h-5 w-5" />
        </button>
      </header>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto overscroll-contain px-4 py-4"
      >
        {content}
      </div>
    </motion.div>
  );
}
