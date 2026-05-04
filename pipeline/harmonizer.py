from dataclasses import dataclass


@dataclass
class UnifiedPost:
    """
    Source-agnostic post schema. All scrapers normalize to this shape
    before entering the pipeline — future sources (Stack Exchange, etc.)
    just need a from_<source> constructor here.
    """
    post_id: str
    source: str
    community: str
    title: str
    body: str
    author_hash: str
    timestamp: str
    score: int
    comment_count: int
    url: str
    flair: str
    top_comments: list[dict]   # [{"body": str, "score": int}]


def harmonize(raw_posts: list[dict]) -> list[UnifiedPost]:
    return [
        UnifiedPost(
            post_id=r["post_id"],
            source=r["source"],
            community=r["community"],
            title=r.get("title", ""),
            body=r.get("body", ""),
            author_hash=r.get("author_hash", ""),
            timestamp=r.get("timestamp", ""),
            score=r.get("score", 0),
            comment_count=r.get("comment_count", 0),
            url=r.get("url", ""),
            flair=r.get("flair", ""),
            top_comments=r.get("top_comments", []),
        )
        for r in raw_posts
    ]
