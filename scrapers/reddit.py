import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import praw
from dotenv import load_dotenv

import config

load_dotenv()


def _hash_author(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:12]


def _scrape_subreddit(reddit: praw.Reddit, subreddit_name: str) -> list[dict]:
    subreddit = reddit.subreddit(subreddit_name)
    posts = []

    # Fetch more than needed to account for posts dropped by ad/bot filtering
    for submission in subreddit.top(time_filter=config.TIME_FILTER, limit=config.POSTS_PER_SUBREDDIT * 2):
        if len(posts) >= config.POSTS_PER_SUBREDDIT:
            break

        # Drop pinned mod announcements and weekly megathreads
        if submission.stickied:
            continue
        # Drop AutoModerator and bot-posted content
        if str(submission.author) in ("AutoModerator", "None", "") or submission.author is None:
            continue
        # Drop mod-distinguished posts (announcements, rule reminders)
        if submission.distinguished:
            continue
        # Drop promoted/sponsored posts (Reddit ads)
        if getattr(submission, "promoted", False):
            continue

        # replace_more(limit=0) skips "load more" expansions — critical for speed
        submission.comments.replace_more(limit=0)

        # Top-level comments only, sorted by score
        top_comments = sorted(
            [
                c for c in submission.comments
                if hasattr(c, "body") and c.body not in ("[deleted]", "[removed]")
            ],
            key=lambda c: c.score,
            reverse=True,
        )[:config.TOP_COMMENTS]

        posts.append({
            "post_id": submission.id,
            "source": "reddit",
            "community": subreddit_name,
            "title": submission.title,
            "body": submission.selftext,
            "author_hash": _hash_author(str(submission.author)),
            "timestamp": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
            "score": submission.score,
            "comment_count": submission.num_comments,
            "url": f"https://reddit.com{submission.permalink}",
            "flair": submission.link_flair_text or "",
            "top_comments": [{"body": c.body, "score": c.score} for c in top_comments],
        })

    return posts


def scrape_all(checkpoint_dir: str) -> list[dict]:
    """
    Scrape all configured subreddits.
    Results are checkpointed to disk per subreddit per day — rerunning the same
    day loads from disk instead of hitting the Reddit API again.
    """
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )

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
            posts = _scrape_subreddit(reddit, subreddit_name)
            with checkpoint_file.open("w") as f:
                for post in posts:
                    f.write(json.dumps(post) + "\n")
            print(f"    → {len(posts)} posts saved")

        all_posts.extend(posts)

    return all_posts
