import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "MailHub",
  description: "All your mailboxes inside Telegram",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#FFFBEB",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Required in Telegram Web/Desktop to expose window.Telegram.WebApp.initData. */}
        <Script
          src="https://telegram.org/js/telegram-web-app.js?1"
          strategy="beforeInteractive"
        />
      </head>
      <body className="min-h-dvh antialiased">
        <div className="app-bg" aria-hidden>
          <div className="grid-bg" aria-hidden />
        </div>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
