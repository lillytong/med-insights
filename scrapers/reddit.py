"""
Reddit scraper using the public Reddit JSON API (no Apify required).

Hits https://www.reddit.com/r/{subreddit}/top.json directly.
This module:
  1. Fetches top posts per subreddit
  2. Filters bots, NSFW, and promoted posts
  3. Checkpoints to disk — rerunning the same day loads from disk
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "med-insights/1.0"})



def _hash_author(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:12]


def _scrape_subreddit(subreddit_name: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit_name}/top.json"
    posts = []
    after = None

    while len(posts) < config.POSTS_PER_SUBREDDIT:
        params = {"limit": 100, "raw_json": 1, "t": config.TIME_FILTER}
        if after:
            params["after"] = after

        resp = _SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()["data"]
        children = data["children"]

        if not children:
            break

        for child in children:
            p = child["data"]

            # Drop bots, AutoModerator, NSFW, promoted
            if p.get("author") in ("AutoModerator", None, ""):
                continue
            if p.get("over_18"):
                continue
            if p.get("is_created_from_ads_ui"):
                continue

            posts.append({
                "post_id": p["id"],
                "source": "reddit",
                "community": p.get("subreddit", subreddit_name),
                "title": p.get("title", ""),
                "body": p.get("selftext", ""),
                "author_hash": _hash_author(p.get("author", "")),
                "author_flair": p.get("author_flair_text", ""),
                "timestamp": datetime.fromtimestamp(
                    p["created_utc"], tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "score": p.get("score", 0),
                "comment_count": p.get("num_comments", 0),
                "url": p.get("url", ""),
                "flair": p.get("link_flair_text") or "",
                "top_comments": [],
            })

            if len(posts) >= config.POSTS_PER_SUBREDDIT:
                break

        after = data.get("after")
        if not after:
            break

        import time
        time.sleep(1)

    return posts


def scrape_all(checkpoint_dir: str) -> list[dict]:
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
            posts = _scrape_subreddit(subreddit_name)
            with checkpoint_file.open("w") as f:
                for post in posts:
                    f.write(json.dumps(post) + "\n")
            print(f"    → {len(posts)} posts saved")

        all_posts.extend(posts)

    return all_posts
