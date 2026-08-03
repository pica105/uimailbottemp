"use client";

import { useEffect } from "react";
import { CategoryTabs } from "@/components/layout/CategoryTabs";
import { MessageList } from "@/components/mail/MessageList";
import { MessageDetail } from "@/components/mail/MessageDetail";
import { useAppStore } from "@/stores/appStore";

export default function InboxPage() {
  const openMessageId = useAppStore((s) => s.openMessageId);
  const setOpenMessage = useAppStore((s) => s.setOpenMessage);
  const setScroll = useAppStore((s) => s.setScroll);

  // Save the list scroll when a message opens, and restore it on close,
  // so returning from a message (or from Settings) lands where you were.
  useEffect(() => {
    if (openMessageId !== null) {
      setScroll("inbox", window.scrollY);
    } else {
      const saved = useAppStore.getState().scroll.inbox;
      window.requestAnimationFrame(() => window.scrollTo(0, saved));
    }
  }, [openMessageId, setScroll]);

  return (
    <main>
      <CategoryTabs />
      <MessageList />
      {openMessageId !== null && (
        <MessageDetail
          key={openMessageId}
          id={openMessageId}
          overlay
          onClose={() => setOpenMessage(null)}
        />
      )}
    </main>
  );
}
