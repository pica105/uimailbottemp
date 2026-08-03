"""Heuristic email classification for providers without native categories.

Gmail already returns its own CATEGORY_* labels; Yandex/IMAP messages are
classified here using lightweight header heuristics — no ML, no network.
"""

from __future__ import annotations

from email.message import Message

from .config import settings


def classify_yandex_message(headers: Message | dict) -> str:
    """Classify an IMAP message into important/promo/spam/social/other.

    Accepts either an email.message.Message or a plain dict with
    'List-Unsubscribe', 'From', and 'Subject' keys.
    """
    if isinstance(headers, Message):
        list_unsubscribe = headers.get("List-Unsubscribe", "") or ""
        from_header = headers.get("From", "") or ""
        subject = headers.get("Subject", "") or ""
    else:
        list_unsubscribe = headers.get("List-Unsubscribe", "") or ""
        from_header = headers.get("From", "") or ""
        subject = headers.get("Subject", "") or ""

    from_lower = from_header.lower()

    # Social-network notifications get their own category even when the
    # provider also adds List-Unsubscribe.
    if any(domain in from_lower for domain in settings.SOCIAL_DOMAINS):
        return "social"

    # Mailing lists and newsletters always carry List-Unsubscribe.
    if list_unsubscribe.strip():
        return "promo"

    # Domain blacklist (senders that are essentially always bulk).
    if any(domain in from_lower for domain in settings.SPAM_DOMAINS):
        return "promo"

    # Keyword blacklist over subject (covers spam in RU and EN).
    subject_lower = subject.lower()
    if any(keyword in subject_lower for keyword in settings.SPAM_KEYWORDS):
        return "spam"

    return "important"
