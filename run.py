"""
med-insights pipeline entrypoint.

Usage:
    python run.py

Flow:
    Scrape → Harmonize → Pre-filter → Haiku filter → Synthesize → Embed → Report
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
from pipeline.embedder import embed_summaries
from store.chroma import upsert_summaries
from pipeline.clusterer import cluster
from dashboard.generate import generate as generate_dashboard
from output.report import save_json, save_markdown
from output.slack import notify


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


    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    synthesis_checkpoint = Path(config.SYNTHESIS_DIR) / f"{date_str}.jsonl"

    processed_ids = _load_cache()
    stats = {}

    # Shortcut: if synthesis checkpoint exists, skip straight to embed
    if synthesis_checkpoint.exists():
        print(f"[1-5/7] Checkpoint found — loading {date_str} summaries directly...", flush=True)
        from pipeline.synthesizer import ThreadSummary
        summaries = [
            ThreadSummary(**json.loads(line))
            for line in synthesis_checkpoint.read_text().splitlines() if line
        ]
        print(f"  {len(summaries)} summaries loaded\n")
    else:
        # 1. Scrape
        print("[1/7] Scraping Reddit...")
        raw_posts = scrape_all(config.RAW_DATA_DIR)
        new_posts = [p for p in raw_posts if p["post_id"] not in processed_ids]
        print(f"  {len(raw_posts)} total scraped, {len(new_posts)} new (not previously processed)\n")

        if not new_posts:
            print("Nothing new to process.")
            return

        # 2. Harmonize
        print("[2/7] Harmonizing...")
        posts = harmonize(new_posts)
        stats["raw"] = len(posts)
        print(f"  {len(posts)} posts\n")

        # 3. Rule-based pre-filter
        print("[3/7] Pre-filtering (rules)...")
        posts, prefilter_dropped = prefilter(posts)
        stats["after_prefilter"] = len(posts)
        print(f"  kept {len(posts)}, dropped {len(prefilter_dropped)}\n")

        if not posts:
            print("All posts dropped at pre-filter stage.")
            return

        # 4. Haiku LLM filter (checkpointed per date)
        filter_checkpoint = Path(config.FILTER_DIR) / f"{date_str}.json"

        if filter_checkpoint.exists():
            kept_ids = set(json.loads(filter_checkpoint.read_text()))
            posts = [p for p in posts if p.post_id in kept_ids]
            print(f"[4/7] Filtering (Haiku)... [cache] {len(posts)} posts loaded\n")
        else:
            print("[4/7] Filtering (Haiku)...")
            posts, llm_dropped = llm_filter(posts)
            filter_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            filter_checkpoint.write_text(json.dumps([p.post_id for p in posts]))
            print(f"  kept {len(posts)}, dropped {len(llm_dropped)}\n")

        stats["after_llm_filter"] = len(posts)

        if not posts:
            print("All posts dropped at LLM filter stage.")
            return

        # 5. Synthesize
        print(f"[5/7] Synthesizing {len(posts)} threads (Sonnet)...")
        summaries = asyncio.run(synthesize_all(posts))
        print(f"  {len(summaries)} summaries generated\n")

    # 6. Embed
    print(f"[6/7] Embedding {len(summaries)} summaries (bge-small)...", flush=True)
    summaries = embed_summaries(summaries)
    print(f"  Done — {len(summaries[0].embedding)} dims per summary\n")

    # 7. Store in vector DB
    print(f"[7/7] Upserting to ChromaDB...", flush=True)
    n_upserted = upsert_summaries(summaries)
    print(f"  {n_upserted} records upserted\n")

    # Save outputs
    json_path = save_json(summaries, config.OUTPUT_DIR)
    md_path = save_markdown(summaries, config.OUTPUT_DIR, stats)

    # Cache processed IDs so reruns skip them
    _save_cache(processed_ids | {s.post_id for s in summaries})

    # Cluster + dashboard
    print("Clustering embeddings...", flush=True)
    clusters = cluster()
    dashboard_path = generate_dashboard(clusters)
    print(f"  Dashboard: {dashboard_path}\n")

    # Notify Slack
    notify(summaries, stats, clusters)

    print("Done.")
    print(f"  JSON:     {json_path}")
    print(f"  Markdown: {md_path}")
    print(f"\n  Pipeline stats: {stats}")


if __name__ == "__main__":
    main()
