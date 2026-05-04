"""
Reddit scraper backed by Apify actor macrocosmos/reddit-scraper.

The actor returns posts and comments as a flat list (differentiated by dataType).
This module:
  1. Runs the actor per subreddit
  2. Separates posts from comments
  3. Groups top comments under their parent post
  4. Checkpoints to disk — rerunning the same day loads from disk
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from apify_client import ApifyClient
from dotenv import load_dotenv

import config

load_dotenv()

ACTOR_ID = "RA1CgWSkuTRNdnOAY"  # macrocosmos/reddit-scraper


def _hash_author(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:12]


def _strip_prefix(reddit_id: str) -> str:
    """Strip Reddit type prefixes: 't3_abc123' → 'abc123'"""
    return reddit_id.split("_", 1)[-1] if "_" in reddit_id else reddit_id


def _scrape_subreddit(client: ApifyClient, subreddit_name: str) -> list[dict]:
    run = client.actor(ACTOR_ID).call(run_input={
        "subreddits": [subreddit_name],
        "sort": config.SORT,
        # limit = total items (posts + comments combined).
        # Each post brings ~TOP_COMMENTS comment items, so multiply accordingly.
        "limit": config.POSTS_PER_SUBREDDIT * (config.TOP_COMMENTS + 1) * 2,
        "proxyConfiguration": {"useApifyProxy": True},
    })

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    # Separate posts from comments
    posts_raw = [i for i in items if i.get("dataType") == "post"]
    comments_raw = [i for i in items if i.get("dataType") == "comment"]

    # Drop bots, AutoModerator, NSFW, promoted
    posts_raw = [
        p for p in posts_raw
        if p.get("username") not in ("AutoModerator", None, "")
        and not p.get("isNsfw", False)
        and not p.get("promoted", False)
    ]

    # Index comments by parent post ID for fast lookup
    comments_by_post: dict[str, list[dict]] = {}
    for c in comments_raw:
        parent = _strip_prefix(c.get("parentId", ""))
        comments_by_post.setdefault(parent, []).append(c)

    posts = []
    for p in posts_raw[:config.POSTS_PER_SUBREDDIT]:
        post_id = _strip_prefix(p["id"])

        # Top-level comments for this post, sorted by score, capped at TOP_COMMENTS
        raw_comments = sorted(
            comments_by_post.get(post_id, []),
            key=lambda c: c.get("score", 0),
            reverse=True,
        )[:config.TOP_COMMENTS]

        community = p.get("communityName", subreddit_name).lstrip("r/")

        posts.append({
            "post_id": post_id,
            "source": "reddit",
            "community": community,
            "title": p.get("title", ""),
            "body": p.get("body", ""),
            "author_hash": _hash_author(p.get("username", "")),
            "timestamp": p.get("createdAt", ""),
            "score": p.get("score", 0),
            "comment_count": p.get("num_comments", 0),
            "url": p.get("url", ""),
            "flair": "",  # not provided by this actor
            "top_comments": [
                {"body": c.get("body", ""), "score": c.get("score", 0)}
                for c in raw_comments
            ],
        })

    return posts


def scrape_all(checkpoint_dir: str) -> list[dict]:
    client = ApifyClient(os.environ["APIFY_API_TOKEN"])

    date_str = datetime.now().strftime("%Y-%m-%d")
    run_dir = Path(checkpoint_dir) / date_str
    run_dir.mkdir(parents=True, exist_ok=True)

    all_posts = []
    for subreddit_name in config.SUBREDDITS:
        checkpoint_file = run_dir / f"{subreddit_name}.jsonl"

        if checkpoint_file.exists():
            print(f"  [cache] r/{subreddit_name} — loading from disk")
            posts = [json.loads(line) for line in checkpoint_file.read_text().splitlines() if line]
        else:
            print(f"  [scrape] r/{subreddit_name} ...")
            posts = _scrape_subreddit(client, subreddit_name)
            with checkpoint_file.open("w") as f:
                for post in posts:
                    f.write(json.dumps(post) + "\n")
            print(f"    → {len(posts)} posts saved")

        all_posts.extend(posts)

    return all_posts
