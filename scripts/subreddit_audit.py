"""
One-off script: scrape 200 posts from each candidate subreddit and save to CSV for noise audit.

Usage:
    python scripts/subreddit_audit.py
"""

import csv
import re
import time

import requests

# Flairs that are obviously noise — skip body entirely
NOISE_FLAIRS = {"humor", "meme", "shitpost", "off topic", "off-topic"}

# Title patterns that are obviously noise
_NOISE_TITLE_RE = re.compile(
    r"\b(happy|congrats|congratulations|welcome|introducing|meme|joke|funny|"
    r"humor|shitpost|rant about nothing|tgif|off.?topic)\b",
    re.IGNORECASE,
)


def _is_obvious_noise(title: str, flair: str) -> bool:
    if flair.lower() in NOISE_FLAIRS:
        return True
    if _NOISE_TITLE_RE.search(title):
        return True
    return False

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "med-insights/1.0"})

SUBREDDITS = [
    "oncology",
    "hematology",
    "endocrinology",
    "nephrology",
    "infectiousdisease",
    "gastroenterology",
    "palliativemedicine",
    "neurology",
]

TARGET_PER_SUB = 200
TIME_FILTER = "year"
OUTPUT = "data/subreddit_audit_batch2.csv"


def fetch_page(subreddit, after=None):
    params = {"limit": 100, "raw_json": 1, "t": TIME_FILTER}
    if after:
        params["after"] = after

    resp = SESSION.get(
        f"https://www.reddit.com/r/{subreddit}/top.json",
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["children"], data.get("after")


def scrape_subreddit(subreddit):
    posts = []
    after = None
    page = 1

    while len(posts) < TARGET_PER_SUB:
        try:
            children, after = fetch_page(subreddit, after)
        except Exception as e:
            print(f"    Error on page {page}: {e}")
            break

        if not children:
            break

        for child in children:
            p = child["data"]
            if p.get("author") in ("AutoModerator", None, ""):
                continue
            if p.get("over_18"):
                continue

            title = p.get("title", "")
            flair = p.get("link_flair_text") or ""
            obvious_noise = _is_obvious_noise(title, flair)

            posts.append({
                "subreddit": subreddit,
                "post_id": p["id"],
                "title": title,
                "body": "" if obvious_noise else p.get("selftext", ""),
                "flair": flair,
                "score": p.get("score", 0),
                "category": "noise" if obvious_noise else "",
            })

        if not after or len(posts) >= TARGET_PER_SUB:
            break

        page += 1
        time.sleep(1)

    return posts[:TARGET_PER_SUB]


def main():
    all_posts = []

    for sub in SUBREDDITS:
        print(f"  Scraping r/{sub}...")
        posts = scrape_subreddit(sub)
        all_posts.extend(posts)
        print(f"    → {len(posts)} posts")
        time.sleep(2)  # be polite between subreddits

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["subreddit", "post_id", "title", "body", "flair", "score", "category"])
        writer.writeheader()
        writer.writerows(all_posts)

    print(f"\n  Total: {len(all_posts)} posts saved to {OUTPUT}")


if __name__ == "__main__":
    main()
