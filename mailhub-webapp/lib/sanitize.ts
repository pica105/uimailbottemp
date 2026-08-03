/**
 * Minimal dependency-free HTML sanitizer for email bodies.
 *
 * Keeps only safe presentational tags and href/src attributes, strips
 * scripts/styles/event handlers and dangerous URL schemes. Not a full
 * DOMPurify replacement, but sufficient for rendering fetched mail.
 */

const ALLOWED_TAGS = new Set([
  "p", "br", "div", "span", "b", "strong", "i", "em", "u", "s", "strike",
  "a", "img", "ul", "ol", "li", "blockquote", "h1", "h2", "h3", "h4",
  "h5", "h6", "pre", "code", "table", "thead", "tbody", "tr", "td", "th",
  "hr", "sup", "sub", "small",
]);

const BLOCK_TAGS = new Set([
  "p", "div", "br", "li", "tr", "blockquote", "h1", "h2", "h3", "h4",
  "h5", "h6", "table", "hr",
]);

const VOID_TAGS = new Set(["br", "img", "hr"]);

function safeUrl(value: string, allowDataImage: boolean): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const lower = trimmed.toLowerCase();
  if (lower.startsWith("javascript:") || lower.startsWith("data:text/html")) {
    return null;
  }
  if (lower.startsWith("data:image/") && allowDataImage) {
    // Only allow a bounded subset of image data URIs (never SVG).
    if (/^data:image\/(png|jpe?g|gif|webp);base64,/.test(lower)) return trimmed;
    return null;
  }
  if (/^(https?:|mailto:|tel:|ftp:)/i.test(trimmed)) return trimmed;
  return null;
}

export function sanitizeHtml(raw: string): string {
  if (!raw) return "";
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "text/html");
  const walk = (node: ChildNode): string[] => {
    const out: string[] = [];
    node.childNodes.forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        out.push(child.textContent ?? "");
        return;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) return;
      const el = child as HTMLElement;
      const tag = el.tagName.toLowerCase();
      if (tag === "script" || tag === "style" || tag === "iframe" || tag === "object") {
        return;
      }
      if (!ALLOWED_TAGS.has(tag)) {
        // Unsupported wrapper: keep its children inline.
        out.push(...walk(el));
        return;
      }
      let attrs = "";
      if (tag === "a") {
        const href = safeUrl(el.getAttribute("href") ?? "", false);
        if (href) {
          attrs = ` href="${escapeAttr(href)}"`;
          const rel = el.getAttribute("target") === "_blank" ? ' target="_blank" rel="noopener noreferrer"' : "";
          attrs += rel;
        } else {
          // Anchor without a safe href renders as plain text.
          out.push(...walk(el));
          return;
        }
      } else if (tag === "img") {
        const src = safeUrl(el.getAttribute("src") ?? "", true);
        if (!src) return;
        const alt = escapeAttr((el.getAttribute("alt") ?? "").slice(0, 200));
        attrs = ` src="${escapeAttr(src)}" alt="${alt}" loading="lazy"`;
      }
      const inner = walk(el).join("");
      if (VOID_TAGS.has(tag)) {
        out.push(`<${tag}${attrs}>`);
      } else {
        out.push(`<${tag}${attrs}>${inner}</${tag}>`);
      }
      if (BLOCK_TAGS.has(tag) && tag !== "br") out.push("\n");
    });
    return out;
  };

  let html = walk(doc.body).join("");
  html = html.replace(/\n{3,}/g, "\n\n");
  return html.trim();
}

function escapeAttr(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
