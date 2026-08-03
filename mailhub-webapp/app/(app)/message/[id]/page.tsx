"use client";

import { use } from "react";
import { MessageDetail } from "@/components/mail/MessageDetail";

export default function MessagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  // Standalone full-screen view (deep link from a Telegram notification):
  // category on the left, close on the right; closing returns to the inbox
  // and highlights this message in the list.
  return <MessageDetail id={Number(id)} standalone />;
}
