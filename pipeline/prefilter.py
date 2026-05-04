"""
Rule-based pre-filter. Zero API cost — runs entirely in Python.
Eliminates obvious noise before any LLM call.

Gates run cheapest-to-most-expensive: deleted → engagement → flair → keyword → length.
Each gate that fires saves downstream cost.
"""

import config
from pipeline.harmonizer import UnifiedPost

# Known off-topic flairs across medical subreddits
BLOCKED_FLAIRS = {
    "meme", "humor", "humour", "shitpost", "off topic", "off-topic",
    "meta", "residency application", "step 1", "step 2", "step 3",
    "match", "img", "funny", "rant", "weekly thread", "daily thread",
}

# Title substrings that signal student/application/non-clinical content.
# Lowercase — compared against post.title.lower()
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
]


def _check(post: UnifiedPost) -> tuple[bool, str]:
    # 1. Deleted or removed
    if post.body in ("[deleted]", "[removed]") and len(post.title.split()) < 8:
        return False, "deleted/removed with short title"

    # 2. Engagement floor — community didn't find it worth engaging with
    if post.score < config.MIN_SCORE and post.comment_count < config.MIN_COMMENTS:
        return False, f"low engagement (score={post.score}, comments={post.comment_count})"

    # 3. Flair blocklist
    if post.flair and post.flair.lower().strip() in BLOCKED_FLAIRS:
        return False, f"blocked flair: {post.flair!r}"

    # 4. Title keyword blocklist
    title_lower = post.title.lower()
    for kw in BLOCKED_TITLE_KEYWORDS:
        if kw in title_lower:
            return False, f"blocked keyword in title: {kw!r}"

    # 5. Body too short to contain a real clinical problem.
    # High-engagement posts skip this gate — the community already validated them.
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
