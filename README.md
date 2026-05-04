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
Reddit (PRAW)
    │
    ▼
Harmonizer          — normalize all sources to a common schema
    │
    ▼
Rule-based pre-filter  — engagement floor, flair/keyword blocklists (zero API cost)
    │
    ▼
Haiku LLM filter    — batched relevance classification (20 posts/call)
    │
    ▼
Sonnet synthesizer  — per-thread structured summary via tool_use
    │
    ▼
Report              — insights_{date}.json + report_{date}.md
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
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — create a "script" app |
| `REDDIT_CLIENT_SECRET` | Same page, shown after creating the app |
| `REDDIT_USER_AGENT` | Any string, e.g. `med-insights/1.0` |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |

## Usage

```bash
python3 run.py
```

The pipeline will print progress at each stage:

```
=== med-insights ===

[1/5] Scraping Reddit...
  [scrape] r/medicine ...
    → 30 posts saved
  ...

[2/5] Harmonizing...
[3/5] Pre-filtering (rules)...
  kept 98, dropped 52

[4/5] Filtering (Haiku)...
  [haiku] batch 1/5 (20 posts)...
  kept 61, dropped 37

[5/5] Synthesizing 61 threads (Sonnet)...
  [sonnet] 61/61 complete

Done.
  JSON:     data/output/insights_2026-05-04.json
  Markdown: data/output/report_2026-05-04.md
```

Output files are written to `data/output/`. The Markdown report is the easiest to read.

## Configuration

All tuneable settings are in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `SUBREDDITS` | 5 Tier-1 subs | Which communities to scrape |
| `POSTS_PER_SUBREDDIT` | 30 | Top posts per subreddit |
| `TIME_FILTER` | `"month"` | Lookback window (`day`, `week`, `month`, `year`) |
| `TOP_COMMENTS` | 10 | Top-level comments included per thread |
| `MIN_SCORE` | 10 | Engagement floor (score) |
| `MIN_COMMENTS` | 5 | Engagement floor (comment count) |
| `FILTER_BATCH_SIZE` | 20 | Posts per Haiku API call |
| `SYNTHESIS_CONCURRENCY` | 5 | Concurrent Sonnet requests |

## Reruns

Post IDs are cached in `data/processed_ids.json` after each run. Rerunning the pipeline skips already-processed posts, so weekly runs only process new content. Raw scraped data is checkpointed to `data/raw/{date}/` — rerunning on the same day loads from disk and does not hit the Reddit API again.
