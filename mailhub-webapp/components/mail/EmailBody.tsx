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
  // Force eager loading: lazy images inside an auto-height iframe would load
  // on scroll and grow the height afterwards, shifting the text being read
  // (the "bottom keeps sliding down" jitter) and leaving the email cut off.
  const eager = html.replace(/\sloading=["']lazy["']/gi, ' loading="eager"');
  return [
    "<!doctype html><html><head><meta charset=\"utf-8\">",
    // Open every mail link externally (via allow-popups) instead of
    // navigating the sandboxed iframe itself — otherwise the email view
    // would be replaced by the external site with no way back.
    "<base target=\"_blank\">",
    `<style>${RESET_STYLE}</style>`,
    "</head><body>",
    eager,
    "</body></html>",
  ].join("");
}

/**
 * Renders the email body visually 1:1 (fonts, images, tables, colors) inside
 * a sandboxed iframe. Sandbox flags keep scripts disabled (no tracking/XSS)
 * while allowing same-origin measurement of the content height and letting
 * mail links open in the external browser.
 *
 * Height measurement is grow-only and stops once the document is stable:
 * polling forever would keep the bottom edge twitching as late images load,
 * and shrinking would snap the page up. The full email is always shown —
 * there is no character/height cut-off here.
 */
export function EmailBody({ html, fallbackText }: Props) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(200);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    const timers: { interval?: number; timeout?: number } = {};
    let lastHeight = 0;
    let stableRuns = 0;
    let hasMeasured = false;

    const stop = () => {
      if (timers.interval !== undefined) window.clearInterval(timers.interval);
      if (timers.timeout !== undefined) window.clearTimeout(timers.timeout);
    };

    const measure = () => {
      const doc = frame.contentDocument;
      if (!doc) return;
      const docHeight = doc.documentElement?.scrollHeight ?? 0;
      const bodyHeight = doc.body?.scrollHeight ?? 0;
      const h = Math.max(docHeight, bodyHeight);
      if (h <= 0) return;
      if (Math.abs(h - lastHeight) < 2) {
        stableRuns += 1;
        // Three stable readings in a row → the document settled, stop polling.
        if (stableRuns >= 3) stop();
      } else {
        stableRuns = 0;
      }
      lastHeight = h;
      if (!hasMeasured) {
        // First reading: set the exact height (may shrink for short emails).
        hasMeasured = true;
        setHeight(h + 8);
      } else {
        // Afterwards grow-only: the bottom edge must never pull back up
        // while images load, or the text being read would jump.
        setHeight((prev) => Math.max(prev, h + 8));
      }
    };

    frame.addEventListener("load", measure);
    timers.interval = window.setInterval(measure, 400);
    timers.timeout = window.setTimeout(stop, 12_000); // hard stop for huge docs
    return () => {
      frame.removeEventListener("load", measure);
      stop();
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
