# med-insights

A tool that scrapes medical communities across social media platforms to surface what doctors are actually talking about — recurring clinical challenges, areas of interest, and day-to-day problems — then synthesizes the key insights.

## What it does

Medical professionals congregate in online communities to discuss cases, share frustrations, and debate clinical decisions. This tool taps into those conversations to extract signal from the noise.

**Data sources:**
- Medical subreddits on Reddit (e.g. r/medicine, r/medicalschool, r/askdocs, specialty-specific subs)
- Facebook groups for doctors and healthcare professionals
- Stack Exchange

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

## Setup

```bash
# Clone the repo
git clone https://github.com/lillytong/med-topics-synthesizer.git
cd med-topics-synthesizer

# Install dependencies
pip install -r requirements.txt

# Configure API credentials
cp .env.example .env
# Fill in Reddit API keys and Facebook credentials
```

## Configuration

Set the following environment variables in `.env`:

```
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=

FACEBOOK_ACCESS_TOKEN=
```

## Usage

```bash
python synthesizer.py --sources reddit facebook --days 7 --output insights.json
```

## Architecture

```
Scrapers → Raw Posts → NLP Processing → Topic Clustering → Synthesis → Report
```

1. **Scrapers** — pull posts and comments from configured sources
2. **NLP Processing** — clean text, extract entities, filter noise
3. **Topic Clustering** — group related discussions using embeddings
4. **Synthesis** — summarize clusters into human-readable insights
