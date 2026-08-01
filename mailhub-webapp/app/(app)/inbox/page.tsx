"use client";

import { CategoryTabs } from "@/components/layout/CategoryTabs";
import { MessageList } from "@/components/mail/MessageList";

export default function InboxPage() {
  return (
    <main>
      <CategoryTabs />
      <MessageList />
    </main>
  );
}
