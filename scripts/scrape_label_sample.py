"""
One-off script: scrape 500 raw posts from r/medicine and export to CSV for labeling.
No filtering applied — everything comes through.

Usage:
    python scripts/scrape_label_sample.py
"""

import csv
import time

import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "med-insights/1.0"})

TARGET = 500
SUBREDDIT = "medicine"
OUTPUT = "data/label_sample.csv"


def fetch_page(after):  # after: str | None
    params = {"limit": 100, "raw_json": 1, "t": "year"}
    if after:
        params["after"] = after

    resp = SESSION.get(
        f"https://www.reddit.com/r/{SUBREDDIT}/top.json",
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["children"], data.get("after")


def main():
    posts = []
    after = None
    page = 1

    while len(posts) < TARGET:
        print(f"  Fetching page {page} (have {len(posts)} so far)...")
        children, after = fetch_page(after)

        if not children:
            print("  No more posts available.")
            break

        for child in children:
            p = child["data"]
            posts.append({
                "post_id": p["id"],
                "title": p.get("title", ""),
                "body": p.get("selftext", ""),
                "flair": p.get("link_flair_text") or "",
                "score": p.get("score", 0),
                "category": "",  # to be filled in
            })

        if not after:
            print("  Reddit has no more pages.")
            break

        page += 1
        time.sleep(1)  # be polite to Reddit's API

    posts = posts[:TARGET]
    print(f"\n  {len(posts)} posts fetched.")

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["post_id", "title", "body", "flair", "score", "category"])
        writer.writeheader()
        writer.writerows(posts)

    print(f"  Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
