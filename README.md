Looking at the diff, I can see two significant changes:

1. `data/chroma/` is now committed to the repo (added to `git add` in the workflow), meaning ChromaDB is persisted directly rather than rebuilt from checkpoints
2. The `restore_from_checkpoints()` call has been removed from `run.py`, confirming that ChromaDB is now persisted rather than rebuilt each run

This is a behavioral change - the previous README described ChromaDB as not persisting between CI jobs and being rebuilt from synthesis checkpoints. Now ChromaDB itself is committed. The cluster data location also moved back to `data/chroma/` based on the new file at `data/chroma/cluster_labels.json`.

The README needs to be updated to reflect this architectural change.

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
- Interactive dashboard with cluster map and sentiment breakdown
- Optional Slack digest with top cluster themes

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
bge-small embedder     — embed each summary locally (bge-small-en-v1.5, 384 dims)
    │
    ▼
ChromaDB               — upsert embeddings + metadata to persistent vector store
    │
    ▼
UMAP + HDBSCAN         — reduce to 2D, discover natural clusters
    │
    ▼
Sonnet cluster labeler — 3-5 word theme label per cluster
    │
    ▼
Dashboard              — dashboard/index.html (self-contained, no server required)
    │
    ▼
Report                 — insights_{date}.json + report_{date}.md
    │
    ▼
Slack (optional)       — digest posted to #med-insights via Incoming Webhook
```

### Data shape at each step

The same post traced through the full pipeline:

**Step 1 — Scrape** (`data/raw/{date}/{subreddit}.jsonl`, one JSON object per line)
```json
{
  "post_id": "1ktz4m2",
  "source": "reddit",
  "community": "Psychiatry",
  "title": "Prior auth denials for clozapine — anyone else seeing this spike?",
  "body": "Third denial this month for a treatment-resistant schizophrenia patient. Insurance wants 'documented failure' of two other antipsychotics even though the patient had agranulocytosis on one of them. The appeals process takes 3-4 weeks minimum. Meanwhile the patient is destabilizing.",
  "author_hash": "a3f9c21b04e7",
  "author_flair": "Psychiatrist (Verified)",
  "timestamp": "2025-11-14T18:32:00Z",
  "score": 847,
  "comment_count": 134,
  "url": "https://www.reddit.com/r/Psychiatry/comments/1ktz4m2/...",
  "flair": "Pharmacology",
  "top_comments": [
    { "body": "Same here. We've started keeping a template appeal letter...", "score": 312 },
    { "body": "The agranulocytosis argument should be an automatic override...", "score": 287 }
  ]
}
```

**Step 2 — Harmonize** (Python `UnifiedPost` dataclass — same fields, guaranteed schema)
```
UnifiedPost(
  post_id      = "1ktz4m2",
  source       = "reddit",
  community    = "Psychiatry",
  title        = "Prior auth denials for clozapine — anyone else seeing this spike?",
  body         = "Third denial this month...",
  author_hash  = "a3f9c21b04e7",
  timestamp    = "2025-11-14T18:32:00Z",
  score        = 847,
  comment_count = 134,
  url          = "https://www.reddit.com/r/Psychiatry/comments/1ktz4m2/...",
  flair        = "Pharmacology",
  top_comments = [{"body": "Same here...", "score": 312}, ...]
)
```

**Step 3 — Rule-based pre-filter** (pass/drop, no transformation)
```
✓ PASS  score=847 ≥ floor, body length ok, flair not blocklisted
```

**Step 4 — Haiku LLM filter** (pass/drop, no transformation)
```
✓ PASS  label=relevant  "Clinical decision-making blocked by prior auth for
        evidence-based medication with documented safety history"
```

**Step 5 — Synthesize** (`data/synthesis/{date}.jsonl`)
```json
{
  "post_id": "1ktz4m2",
  "community": "Psychiatry",
  "url": "https://www.reddit.com/r/Psychiatry/comments/1ktz4m2/...",
  "comment_count": 134,
  "timestamp": "2025-11-14T18:32:00Z",
  "headline": "Prior authorization barriers are delaying clozapine access for treatment-resistant schizophrenia patients despite documented contraindications to alternatives.",
  "clinical_problem": "Insurers are requiring documented failure of two antipsychotics before approving clozapine, even when patients have a history of agranulocytosis that makes those alternatives contraindicated. Appeals take 3-4 weeks, leaving unstable patients without treatment.",
  "key_findings": [
    "Step-therapy requirements are being applied rigidly without accounting for documented adverse drug history",
    "Psychiatrists report a recent spike in denials specifically for clozapine",
    "The appeals process timeline (3-4 weeks) causes meaningful clinical harm for psychotic patients",
    "Physicians are developing informal workarounds (template appeal letters) rather than a systemic fix"
  ],
  "unmet_need": "Automated prior auth override pathway when contraindication to required step-therapy drugs is documented in the medical record.",
  "specialty_tags": ["psychiatry", "pharmacology"],
  "sentiment": "frustrated",
  "embedding": []
}
```

**Step 6 — Embed** (384-dim bge-small vector added to the summary object, runs locally)
```json
{
  "post_id": "1ktz4m2",
  "headline": "Prior authorization barriers are delaying clozapine access...",
  "embedding": [0.0412, -0.0837, 0.1204, -0.0531, 0.0093, "...379 more floats..."]
}
```

**Step 7 — ChromaDB** (what gets stored in the vector index)
```json
{
  "id": "1ktz4m2",
  "document": "Prior authorization barriers are delaying clozapine access for treatment-resistant schizophrenia patients. Insurers are requiring documented failure of two antipsychotics... Automated prior auth override pathway when contraindication is documented.",
  "embedding": [0.0412, -0.0837, ...],
  "metadata": {
    "community":      "Psychiatry",
    "sentiment":      "frustrated",
    "specialty_tags": "psychiatry, pharmacology",
    "comment_count":  134,
    "timestamp":      "2025-11-14T18:32:00Z",
    "url":            "https://www.reddit.com/r/Psychiatry/comments/1ktz4m2/...",
    "headline":       "Prior authorization barriers are delaying clozapine access...",
    "unmet_need":     "Automated prior auth override pathway when contraindication is documented."
  }
}
```

**Step 8 — Cluster** (UMAP + HDBSCAN → Sonnet labels; `cluster_id`, `umap_x`, `umap_y` written back to ChromaDB metadata)
```
  [clusterer] 14 clusters found, 37 noise points
  [clusterer] labeling cluster 0 (89 posts)... "Prior auth blocking biologics"
  [clusterer] labeling cluster 1 (74 posts)... "Burnout and staffing shortages"
  ...
```

**Step 9 — Dashboard** (`dashboard/index.html` — self-contained, no server required)

A single HTML file with embedded D3 visualizations:
- Bubble chart: one bubble per cluster, sized by post count, colored by dominant sentiment
- Specialty breakdown bar chart
- Sentiment distribution
- Click-to-explore cluster detail panel

**Step 10 — Report** (`data/output/{date}/insights_{date}.json`, one entry per summary)
```json
{
  "post_id": "1ktz4m2",
  "community": "Psychiatry",
  "headline": "Prior authorization barriers are delaying clozapine access for treatment-resistant schizophrenia patients.",
  "clinical_problem": "Insurers are requiring documented failure of two antipsychotics...",
  "key_findings": ["Step-therapy requirements applied rigidly...", "..."],
  "unmet_need": "Automated prior auth override pathway when contraindication is documented.",
  "specialty_tags": ["psychiatry", "pharmacology"],
  "sentiment": "frustrated",
  "comment_count": 134,
  "timestamp": "2025-11-14T18:32:00Z",
  "url": "https://www.reddit.com/r/Psychiatry/comments/1ktz4m2/..."
}
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

Clustering requires two additional packages:
```bash
pip install hdbscan umap-learn
```

**3. Configure credentials**
```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `SLACK_WEBHOOK_URL` | [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks) — optional, enables run digest in #med-insights |

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

[6/7] Embedding 934 summaries (bge-small)...
  Done — 384 dims per summary

[7/7] Upserting to ChromaDB...
  934 records upserted

Clustering embeddings...
  [clusterer] fetching 934 records from ChromaDB...
  [clusterer] UMAP: 384 → 2D...
  [clusterer] HDBSCAN (min_cluster_size=5)...
  [clusterer] 14 clusters found, 37 noise points
  [clusterer] labeling cluster 0 (89 posts)...
  ...
  Dashboard: dashboard/index.html

  [slack] notification sent to #med-insights

Done.
  JSON:     data/output/2026-05-07/insights_2026-05-07.json
  Markdown: data/output/2026-05-07/report_2026-05-07.md
```

Output files are written to `data/output/{date}/`. The Markdown report is the easiest to read. The dashboard is written to `dashboard/index.html` — open it directly in a browser, no server required.

If `SLACK_WEBHOOK_URL` is set, a digest is posted to #med-insights after each run containing run stats, specialty breakdown, sentiment distribution, top unmet needs, top cluster themes, and highlighted threads. If the variable is unset, the notification is skipped silently.

## Automated weekly runs

The pipeline runs automatically every Monday at 9am UTC (5am ET) via GitHub Actions. Each automated run:

- Uses the default `POSTS_PER_SUBREDDIT=100` and `TIME_FILTER=week` settings from `config.py`
- Requires `ANTHROPIC_API_KEY` and (optionally) `SLACK_WEBHOOK_URL` set as repository secrets
- Commits updated synthesis checkpoints, cluster labels, cluster assignments, the ChromaDB store, and the refreshed dashboard back to `main`
- Can also be triggered manually from the Actions tab via **workflow_dispatch**

The ChromaDB vector store (`data/chroma/`) is committed to the repo and persists across CI runs, so each automated run picks up exactly where the last one left off — no rebuild from checkpoints required.

## Configuration

All tuneable settings are in `config.py`:

| Setting | Default | Env override | Description |
|---|---|---|---|
| `SUBREDDITS` | 8 subs | — | Which communities to scrape |
| `POSTS_PER_SUBREDDIT` | 100 | `POSTS_PER_SUBREDDIT` | Top posts per subreddit |
| `TIME_FILTER` | `"week"` | `TIME_FILTER` | Lookback window (`day`, `week`, `month`, `year`) |
| `TOP_COMMENTS` | 10 | — | Top-level comments included per thread |
| `MAX_COMMENT_WORDS` | 150 | — | Words per comment sent to LLM |
| `FILTER_BATCH_SIZE` | 20 | — | Posts per Haiku API call |
| `SYNTHESIS_CONCURRENCY` | 2 | — | Concurrent Sonnet requests |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | — | Local model, no API key, 384 dims |
| `EMBEDDING_BATCH_SIZE` | 64 | — | Summaries per encode batch |

`POSTS_PER_SUBREDDIT` and `TIME_FILTER` can be overridden at runtime without editing `config.py`:

```bash
POSTS_PER_SUBREDDIT=500 TIME_FILTER=year python run.py
```

### Clustering

Clustering is controlled by a single parameter passed to `pipeline/clusterer.py`:

| Parameter | Default | Description |
|---|---|---|
| `min_cluster_size` | `5` | Minimum posts to form a cluster (HDBSCAN). Lower = more, smaller clusters. Raise for fewer, broader themes. |

Posts that don't belong to any cluster are labeled noise and excluded from the dashboard bubble chart and Slack theme summary.

## Reruns & resumability

The pipeline has three layers of caching to avoid redundant work:

| Layer | Location | What it skips |
|---|---|---|
| Scrape cache | `data/raw/{date}/{su