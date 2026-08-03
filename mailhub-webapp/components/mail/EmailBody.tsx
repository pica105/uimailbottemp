"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  /** Raw email HTML body (may include full <html> documents). */
  html: string;
  /** Plain-text fallback shown when there is no HTML body. */
  fallbackText?: string | null;
}

/**
 * A tiny reset stylesheet injected around the email so it renders close to
 * how it looks in the mailbox while staying readable on the app background.
 */
const RESET_STYLE = `
  html, body { margin: 0; padding: 0; background: transparent; }
  body { color: inherit; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; font-size: 15px; line-height: 1.5; word-wrap: break-word; }
  img { max-width: 100% !important; height: auto !important; }
  a { word-break: break-word; }
  table { max-width: 100% !important; }
  * { box-sizing: border-box; }
`;

function buildSrcDoc(html: string): string {
  return [
    "<!doctype html><html><head><meta charset=\"utf-8\">",
    // Open every mail link externally (via allow-popups) instead of
    // navigating the sandboxed iframe itself — otherwise the email view
    // would be replaced by the external site with no way back.
    "<base target=\"_blank\">",
    `<style>${RESET_STYLE}</style>`,
    "</head><body>",
    html,
    "</body></html>",
  ].join("");
}

/**
 * Renders the email body visually 1:1 (fonts, images, tables, colors) inside
 * a sandboxed iframe. Sandbox flags keep scripts disabled (no tracking/XSS)
 * while allowing same-origin measurement of the content height and letting
 * mail links open in the external browser.
 */
export function EmailBody({ html, fallbackText }: Props) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(320);

  // Re-measure once the document (and its images) have loaded; images can
  // change the height well after the initial load event.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    const measure = () => {
      const doc = frame.contentDocument;
      if (!doc) return;
      const docHeight = doc.documentElement?.scrollHeight ?? 0;
      const bodyHeight = doc.body?.scrollHeight ?? 0;
      const next = Math.max(docHeight, bodyHeight);
      if (next > 0) setHeight(next + 8);
    };

    frame.addEventListener("load", measure);
    const interval = window.setInterval(measure, 600);
    const stop = window.setTimeout(() => window.clearInterval(interval), 10_000);
    return () => {
      frame.removeEventListener("load", measure);
      window.clearInterval(interval);
      window.clearTimeout(stop);
    };
  }, [html]);

  if (!html.trim()) {
    return (
      <div className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground/90">
        {fallbackText || ""}
      </div>
    );
  }

  return (
    <iframe
      ref={frameRef}
      title="Message body"
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      srcDoc={buildSrcDoc(html)}
      className="w-full border-0 bg-transparent"
      style={{ height }}
      scrolling="no"
    />
  );
}
