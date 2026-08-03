"""Convert raw email bodies into Telegram-safe HTML notifications.

Rules applied here (per the product instructions):
- Hyperlinks embedded in text keep their anchor text and become real
  Telegram <a> links.
- A bare/standalone URL is made into a link; when the URL is longer than
  12 characters (ignoring the ``https://`` / ``http://`` scheme prefix,
  ``www.`` counts toward the length) the link text shows the first 9
  characters followed by ``...``.
- No other styling (bold/italic/sizes) is preserved: the notification body
  is plain text with links, so it looks like the raw message.
- The first http(s) <img> URL is extracted so the caller can send a photo
  alongside the text.
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser

# Splits on URLs while keeping the delimiter (group 1).
_URL_SPLIT_RE = re.compile(
    r"((?:https?://|www\.)[^\s<>\"']+)", re.IGNORECASE
)
_TRAILING_PUNCT = "),.;:!?\\]}\"'"

_BLOCK_TAGS = {
    "p", "div", "tr", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "ul", "ol", "section", "article", "header", "footer", "hr",
    "dl", "dd", "dt", "pre",
}

# (kind, ...) segment kinds:
#   ("text", value)
#   ("link", href, display)
#   ("nl",)
Segment = tuple


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip(_TRAILING_PUNCT)
    if url.lower().startswith("www."):
        url = "https://" + url
    return url


def shorten_url_display(url: str) -> str:
    """Shorten a bare URL for display: 9 chars + '...' when it is long.

    The scheme (https://, http://) is ignored when counting; ``www.`` counts
    toward the length. URLs of 12 or fewer characters are shown in full.
    """
    stripped = url
    if stripped.lower().startswith("https://"):
        stripped = stripped[8:]
    elif stripped.lower().startswith("http://"):
        stripped = stripped[7:]
    if len(stripped) <= 12:
        return stripped
    return stripped[:9] + "..."


def _split_urls(text: str) -> list[tuple[str, str]]:
    """Split text into ('text', s) / ('url', url) tokens."""
    parts = _URL_SPLIT_RE.split(text)
    out: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 1:
            out.append(("url", part))
        else:
            out.append(("text", part))
    return out


class _BodyParser(HTMLParser):
    """Walk an HTML email body producing Telegram-safe segments."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.segments: list[Segment] = []
        self.image_urls: list[str] = []
        self._skip_depth = 0
        self._a_href: str | None = None
        self._a_buffer: list[str] = []

    # -- helpers --------------------------------------------------------
    def _emit_text(self, text: str) -> None:
        text = text.replace("\r\n", " ").replace("\n", " ")
        text = re.sub(r"[ \t]+", " ", text)
        if not text.strip():
            return
        for kind, value in _split_urls(text):
            if kind == "url":
                self.segments.append(
                    ("link", _normalize_url(value), shorten_url_display(value))
                )
            else:
                stripped = value.strip()
                if stripped:
                    self.segments.append(("text", stripped + (" " if value.endswith(" ") else "")))

    def _emit_link(self, href: str, display: str) -> None:
        href = _normalize_url(href)
        display = re.sub(r"\s+", " ", display).strip()
        if not display:
            display = shorten_url_display(href)
        elif display.strip() == href or display == _normalize_url(href):
            display = shorten_url_display(href)
        self.segments.append(("link", href, display))

    def _append_newline(self) -> None:
        if self.segments and self.segments[-1] != ("nl",):
            self.segments.append(("nl",))

    # -- parser callbacks ----------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "head", "iframe", "object", "embed", "noscript"):
            self._skip_depth += 1
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs if k}
        if tag == "a":
            href = attr_map.get("href") or ""
            if href:
                self._a_href = href
                self._a_buffer = []
            return
        if tag == "img":
            src = attr_map.get("src") or ""
            if src.startswith(("https://", "http://")):
                self.image_urls.append(src)
            return
        if tag == "br":
            self._append_newline()
            return
        if tag in _BLOCK_TAGS:
            self._append_newline()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "head", "iframe", "object", "embed", "noscript"):
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag == "a" and self._a_href:
            self._emit_link(self._a_href, "".join(self._a_buffer))
            self._a_href = None
            self._a_buffer = []
            return

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._a_href is not None:
            self._a_buffer.append(data)
            return
        self._emit_text(data)


def _segments_from_html(html: str) -> tuple[list[Segment], list[str]]:
    parser = _BodyParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed email HTML must not break sync
        parser.segments = []
        parser.image_urls = []
    return parser.segments, parser.image_urls


def _segments_from_plain(text: str) -> list[Segment]:
    segments: list[Segment] = []
    for line in (text or "").splitlines():
        if not line.strip():
            segments.append(("nl",))
            continue
        for kind, value in _split_urls(line):
            if kind == "url":
                segments.append(("link", _normalize_url(value), shorten_url_display(value)))
            elif value.strip():
                segments.append(("text", value))
        segments.append(("nl",))
    return segments


def body_to_segments(body_html: str | None, body_text: str | None) -> tuple[list[Segment], list[str]]:
    """Return (segments, image_urls) from the richest available body part."""
    if body_html:
        segments, images = _segments_from_html(body_html)
        if segments:
            return segments, images
    return _segments_from_plain(body_text or ""), []


def visible_len(html: str) -> int:
    """Visible character count of a Telegram-HTML string (tags stripped)."""
    return len(re.sub(r"<[^>]+>", "", html))


def render_segments(segments: list[Segment], max_chars: int | None = None) -> str:
    """Render segments to a Telegram-safe HTML string, truncating at
    ``max_chars`` visible characters without cutting inside a tag."""
    out: list[str] = []
    visible = 0
    truncated = False

    for seg in segments:
        if seg[0] == "nl":
            if out and not out[-1].endswith("\n") and not out[-1].endswith(" "):
                out.append("\n")
            continue
        if max_chars is not None and visible >= max_chars:
            truncated = True
            break

        remaining = None if max_chars is None else max_chars - visible
        if seg[0] == "text":
            text = seg[1]
            if remaining is not None and remaining <= 0:
                truncated = True
                break
            if remaining is not None and len(text) > remaining:
                text = text[:remaining].rstrip()
                truncated = True
            if text:
                out.append(_html.escape(text))
                visible += len(text)
        elif seg[0] == "link":
            href, display = seg[1], seg[2]
            if remaining is not None and remaining <= 0:
                truncated = True
                break
            if remaining is not None and len(display) > remaining:
                display = display[:remaining].rstrip()
                truncated = True
            if display:
                out.append(
                    f'<a href="{_html.escape(href, quote=True)}">'
                    f"{_html.escape(display)}</a>"
                )
                visible += len(display)
        if truncated:
            break

    if truncated:
        out.append("…")

    text = "".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip("\n")


def convert_body(
    body_html: str | None,
    body_text: str | None,
    max_chars: int | None = None,
) -> tuple[str, str | None]:
    """Return (telegram_html, first_image_url) for a mail body."""
    segments, images = body_to_segments(body_html, body_text)
    image = next((u for u in images if u.startswith(("https://", "http://"))), None)
    return render_segments(segments, max_chars), image
