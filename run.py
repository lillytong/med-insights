"""
med-insights pipeline entrypoint.

Usage:
    python run.py

Flow:
    Scrape → Harmonize → Pre-filter → Haiku filter → Synthesize → Report
"""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import config
from scrapers.reddit import scrape_all
from pipeline.harmonizer import harmonize
from pipeline.prefilter import prefilter
from pipeline.filter import llm_filter
from pipeline.synthesizer import synthesize_all
from output.report import save_json, save_markdown


def _load_cache() -> set[str]:
    p = Path(config.CACHE_FILE)
    if p.exists():
        return set(json.loads(p.read_text()))
    return set()


def _save_cache(processed_ids: set[str]) -> None:
    Path(config.CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(config.CACHE_FILE).write_text(json.dumps(list(processed_ids)))


def main():
    print("\n=== med-insights ===\n")

    processed_ids = _load_cache()

    # 1. Scrape
    print("[1/5] Scraping Reddit...")
    raw_posts = scrape_all(config.RAW_DATA_DIR)
    new_posts = [p for p in raw_posts if p["post_id"] not in processed_ids]
    print(f"  {len(raw_posts)} total scraped, {len(new_posts)} new (not previously processed)\n")

    if not new_posts:
        print("Nothing new to process.")
        return

    # 2. Harmonize
    print("[2/5] Harmonizing...")
    posts = harmonize(new_posts)
    stats = {"raw": len(posts)}
    print(f"  {len(posts)} posts\n")

    # 3. Rule-based pre-filter
    print("[3/5] Pre-filtering (rules)...")
    posts, prefilter_dropped = prefilter(posts)
    stats["after_prefilter"] = len(posts)
    print(f"  kept {len(posts)}, dropped {len(prefilter_dropped)}\n")

    if not posts:
        print("All posts dropped at pre-filter stage.")
        return

    # 4. Haiku LLM filter
    print("[4/5] Filtering (Haiku)...")
    posts, llm_dropped = llm_filter(posts)
    stats["after_llm_filter"] = len(posts)
    print(f"  kept {len(posts)}, dropped {len(llm_dropped)}\n")

    if not posts:
        print("All posts dropped at LLM filter stage.")
        return

    # 5. Synthesize
    print(f"[5/5] Synthesizing {len(posts)} threads (Sonnet)...")
    summaries = asyncio.run(synthesize_all(posts))
    print(f"  {len(summaries)} summaries generated\n")

    # Save outputs
    json_path = save_json(summaries, config.OUTPUT_DIR)
    md_path = save_markdown(summaries, config.OUTPUT_DIR, stats)

    # Cache processed IDs so reruns skip them
    _save_cache(processed_ids | {p.post_id for p in posts})

    print("Done.")
    print(f"  JSON:     {json_path}")
    print(f"  Markdown: {md_path}")
    print(f"\n  Pipeline stats: {stats}")


if __name__ == "__main__":
    main()
