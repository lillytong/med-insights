# med-insights

A tool that scrapes medical communities across social media platforms to surface what doctors are actually talking about — recurring clinical challenges, areas of interest, and day-to-day problems — then synthesizes the key insights.

## What it does

Medical professionals congregate in online communities to discuss cases, share frustrations, and debate clinical decisions. This tool taps into those conversations to extract signal from the noise.

**Data sources:**
- Medical subreddits on Reddit (e.g. r/medicine, r/emergencymedicine, r/hospitalist, specialty-specific subs)
- Stack Exchange (coming soon)

**What it surfaces:**
- Recurring clinical challenges physicians face
- Topics generating the most discussion and engagement
- Common pain points and workflow frustrations
- Areas of clinical uncertainty or debate
- Emerging trends in medical practice

**Output:**
- Synthesized summaries of key themes across communities
- Ranked topics by frequency and engagement
- Insights segmented by specialty or community

## Use cases

- Healthcare product teams identifying unmet clinical needs
- Medical educators understanding where knowledge gaps exist
- Researchers spotting areas of clinical uncertainty
- Anyone trying to understand what problems doctors actually have

## Architecture

```
Reddit JSON API
    │
    ▼
Harmonizer             — normalize all sources to a common schema
    │
    ▼
Rule-based pre-filter  — engagement floor, flair/keyword blocklists (zero API cost)
    │
    ▼
Haiku LLM filter       — batched relevance classification (20 posts/call)
    │
    ▼
Sonnet synthesizer     — per-thread structured summary via tool_use
    │                     checkpointed to data/synthesis/{date}.jsonl
    ▼
Voyage embedder        — embed each summary (voyage-3-lite, 512 dims)
    │
    ▼
ChromaDB               — upsert embeddings + metadata to persistent vector store
    │
    ▼
Report                 — insights_{date}.json + report_{date}.md
```

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/lillytong/med-insights.git
cd med-insights
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure credentials**
```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `VOYAGE_API_KEY` | [dash.voyageai.com](https://dash.voyageai.com) |

## Usage

```bash
python3 run.py
```

The pipeline will print progress at each stage:

```
=== med-insights ===

[1/5] Scraping Reddit...
  [cache] r/psychiatry — loading from disk
  ...

[2/5] Harmonizing...
[3/5] Pre-filtering (rules)...
  kept 934, dropped 1960

[4/5] Filtering (Haiku)...
  [haiku] batch 1/47 (20 posts)...
  kept 934, dropped 0

[5/6] Synthesizing 934 threads (Sonnet)...
  [checkpoint] 200 already done, 734 remaining
  [sonnet] 734/734 complete

[6/7] Embedding 934 summaries (Voyage)...
  Done — 512 dims per summary

[7/7] Upserting to ChromaDB...
  934 records upserted

Done.
  JSON:     data/output/insights_2026-05-07.json
  Markdown: data/output/report_2026-05-07.md
```

Output files are written to `data/output/`. The Markdown report is the easiest to read.

## Configuration

All tuneable settings are in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `SUBREDDITS` | 8 subs | Which communities to scrape |
| `POSTS_PER_SUBREDDIT` | 500 | Top posts per subreddit |
| `TIME_FILTER` | `"year"` | Lookback window (`day`, `week`, `month`, `year`) |
| `TOP_COMMENTS` | 10 | Top-level comments included per thread |
| `MAX_COMMENT_WORDS` | 150 | Words per comment sent to LLM |
| `FILTER_BATCH_SIZE` | 20 | Posts per Haiku API call |
| `SYNTHESIS_CONCURRENCY` | 2 | Concurrent Sonnet requests |
| `EMBEDDING_MODEL` | `voyage-3-lite` | Voyage model (512 dims) |
| `EMBEDDING_BATCH_SIZE` | 128 | Posts per Voyage API call |

## Reruns & resumability

The pipeline has three layers of caching to avoid redundant work:

| Layer | Location | What it skips |
|---|---|---|
| Scrape cache | `data/raw/{date}/{subreddit}.jsonl` | Re-hitting the Reddit API on same-day reruns |
| Synthesis checkpoint | `data/synthesis/{date}.jsonl` | Re-synthesizing posts that already completed |
| Processed ID cache | `data/processed_ids.json` | Posts successfully synthesized in prior runs |

If the pipeline is interrupted mid-synthesis (crash, rate limit, Ctrl+C), rerunning on the same day will skip already-completed summaries and pick up from where it left off.
