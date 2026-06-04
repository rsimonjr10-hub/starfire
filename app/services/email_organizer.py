"""
STARFIRE Email Organizer
Spam/promo detection, auto-deletion, and inbox organization.

Uses Gmail's built-in category labels as the primary classification signal
(they're powered by Google's own ML), supplemented by heuristics for messages
that haven't been categorized yet.
"""

import re
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

# Gmail system label IDs for built-in categories
CATEGORY_LABELS = {
    "spam":       "SPAM",
    "promotions": "CATEGORY_PROMOTIONS",
    "social":     "CATEGORY_SOCIAL",
    "updates":    "CATEGORY_UPDATES",
    "forums":     "CATEGORY_FORUMS",
}

# Sender patterns that are almost always promotional
_PROMO_SENDER_RE = re.compile(
    r"(newsletter|noreply|no-reply|notify|notification|marketing|promo|offers|deals|"
    r"updates|info|donotreply|do-not-reply|hello|team|support|news)\s*@",
    re.IGNORECASE,
)

# Subject keywords that strongly indicate promotional content
_PROMO_SUBJECT_RE = re.compile(
    r"\b(\d+\s*%\s*off|discount|coupon|sale\b|deals?|flash\s+sale|special\s+offer|"
    r"limited.?time|exclusive|free\s+shipping|promo\s+code|shop\s+now|buy\s+now|"
    r"your\s+order|order\s+confirmation|receipt)\b",
    re.IGNORECASE,
)

# Unsubscribe link — the single strongest promo signal
_UNSUB_RE = re.compile(r"unsubscribe|opt.?out|manage\s+(your\s+)?preferences", re.IGNORECASE)


def classify_message(msg: dict) -> str:
    """
    Classify a message dict as 'spam' | 'promo' | 'normal'.
    msg should contain keys: labelIds (list), from, subject, snippet.
    """
    labels = msg.get("labelIds") or msg.get("labels") or []

    if "SPAM" in labels:
        return "spam"
    if "CATEGORY_PROMOTIONS" in labels:
        return "promo"
    if any(l in labels for l in ("CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS")):
        return "promo"

    sender  = msg.get("from", "")
    subject = msg.get("subject", "")
    snippet = msg.get("snippet", "")
    body    = snippet

    if _UNSUB_RE.search(body):
        return "promo"
    if _PROMO_SENDER_RE.search(sender):
        return "promo"
    if _PROMO_SUBJECT_RE.search(subject):
        return "promo"

    return "normal"


def get_inbox_stats(gmail) -> dict:
    """Return estimated message counts per Gmail category."""
    stats = {}
    for cat, label in CATEGORY_LABELS.items():
        stats[cat] = gmail.count_messages(f"label:{label}")
    stats["inbox_unread"] = gmail.count_messages("is:unread in:inbox")
    stats["inbox_total"]  = gmail.count_messages("in:inbox")
    return stats


def clean_spam(gmail, max_messages: int = 500) -> dict:
    """
    Permanently delete all messages in the spam folder.
    Returns {"deleted": int, "errors": int}.
    """
    ids = gmail.list_category("spam", max_results=max_messages)
    if not ids:
        return {"deleted": 0, "errors": 0, "message": "Spam folder is already empty."}
    result = gmail.batch_delete(ids)
    logger.info("email_spam_cleaned", deleted=result.get("deleted", 0))
    return result


def clean_category(gmail, category: str, action: str = "archive", max_messages: int = 200) -> dict:
    """
    Clean a Gmail category by archiving or deleting all messages in it.

    category: 'promotions' | 'social' | 'updates' | 'forums'
    action:   'archive'  (removes from inbox, keeps in All Mail)
              'delete'   (moves to trash)
    """
    if category not in CATEGORY_LABELS or category == "spam":
        return {"error": f"Unknown category: {category}. Use promotions/social/updates/forums."}

    ids = gmail.list_category(category, max_results=max_messages)
    if not ids:
        return {"count": 0, "action": action, "message": f"No {category} emails found."}

    if action == "delete":
        result = gmail.batch_trash(ids)
        count  = result.get("trashed", 0)
        logger.info("email_category_deleted", category=category, count=count)
        return {"count": count, "action": "deleted", "errors": result.get("errors", 0)}
    else:
        result = gmail.batch_archive(ids)
        count  = result.get("archived", 0)
        logger.info("email_category_archived", category=category, count=count)
        return {"count": count, "action": "archived", "errors": result.get("errors", 0)}


def organize_inbox(gmail, rules: Optional[dict] = None) -> dict:
    """
    Full inbox organization pass.

    Default rules:
      delete_spam=True         — permanently delete spam
      archive_promotions=True  — archive promotional emails
      archive_social=False     — leave social notifications
      archive_updates=False    — leave update emails
      max_per_category=200     — cap per category to avoid timeouts

    Returns a summary dict with per-category results and a total_cleaned count.
    """
    cfg = {
        "delete_spam":        True,
        "archive_promotions": True,
        "archive_social":     False,
        "archive_updates":    False,
        "max_per_category":   200,
    }
    if rules:
        cfg.update(rules)

    summary = {}

    if cfg["delete_spam"]:
        summary["spam"] = clean_spam(gmail, max_messages=cfg["max_per_category"])

    if cfg["archive_promotions"]:
        summary["promotions"] = clean_category(
            gmail, "promotions", "archive", cfg["max_per_category"]
        )

    if cfg["archive_social"]:
        summary["social"] = clean_category(
            gmail, "social", "archive", cfg["max_per_category"]
        )

    if cfg["archive_updates"]:
        summary["updates"] = clean_category(
            gmail, "updates", "archive", cfg["max_per_category"]
        )

    total_cleaned = 0
    for v in summary.values():
        total_cleaned += v.get("deleted", 0) + v.get("count", 0)

    logger.info("inbox_organized", total_cleaned=total_cleaned, categories=list(summary.keys()))
    return {"summary": summary, "total_cleaned": total_cleaned}
