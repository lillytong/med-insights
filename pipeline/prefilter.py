"""
Rule-based pre-filter. Zero API cost — runs entirely in Python.
Eliminates obvious noise before any LLM call.

Gates: deleted → link-only → engagement → keyword → length.
Note: flair filtering removed — not provided by the Apify actor.
"""

import re

import config
from pipeline.harmonizer import UnifiedPost

_URL_RE = re.compile(r"https?://\S+")

BLOCKED_TITLE_KEYWORDS = [
    # Exams & applications
    "usmle", "step 1", "step 2", "step 3", "step1", "step2", "step3",
    "match day", "rank list", "residency application", "interview season",
    "nrmp", "soap", "img ",
    # Entertainment
    "grey's anatomy", "house md", "the good doctor", "scrubs",
    # Pure social
    "happy doctors day", "congratulations", "welcome to the sub",
    # Explicit humor/meme
    "[meme]", "[humor]", "[shitpost]",
    # Recurring mod megathreads
    "weekly thread", "biweekly", "monthly thread", "daily thread",
]


def _is_link_only(body: str) -> bool:
    """True if the body has no substantive text beyond URLs."""
    text = _URL_RE.sub("", body).strip()
    return len(text.split()) < 10


def _check(post: UnifiedPost) -> tuple[bool, str]:
    # 1. Deleted or removed
    if post.body in ("[deleted]", "[removed]") and len(post.title.split()) < 8:
        return False, "deleted/removed with short title"

    # 2. Link-only post — body is empty or just a URL (YouTube, news article, etc.)
    if _is_link_only(post.body):
        return False, "link-only post (no substantive body text)"

    # 3. Engagement floor
    if post.score < config.MIN_SCORE and post.comment_count < config.MIN_COMMENTS:
        return False, f"low engagement (score={post.score}, comments={post.comment_count})"

    # 4. Title keyword blocklist
    title_lower = post.title.lower()
    for kw in BLOCKED_TITLE_KEYWORDS:
        if kw in title_lower:
            return False, f"blocked keyword in title: {kw!r}"

    # 5. Body too short to contain a real clinical problem.
    # High-engagement posts skip this gate — community already validated them.
    body_words = len(post.body.split())
    title_words = len(post.title.split())
    high_engagement = post.score >= 50 or post.comment_count >= 20
    if not high_engagement and body_words < config.MIN_BODY_WORDS and title_words < 8:
        return False, f"too short (body={body_words} words, title={title_words} words)"

    return True, "passed"


def prefilter(posts: list[UnifiedPost]) -> tuple[list[UnifiedPost], list[dict]]:
    kept, dropped = [], []
    for post in posts:
        relevant, reason = _check(post)
        if relevant:
            kept.append(post)
        else:
            dropped.append({"post_id": post.post_id, "title": post.title, "reason": reason})
    return kept, dropped
