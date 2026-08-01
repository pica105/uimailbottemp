"use client";

import { use } from "react";
import { MessageDetail } from "@/components/mail/MessageDetail";

export default function MessagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <main>
      <MessageDetail id={Number(id)} />
    </main>
  );
}
