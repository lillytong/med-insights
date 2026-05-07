"""
Slack notification for med-insights pipeline runs.

Posts a digest to #med-insights via Incoming Webhook after each run.
Set SLACK_WEBHOOK_URL in .env to enable. If unset, notification is skipped silently.

Message structure:
  - Run stats (scraped → filtered → synthesized)
  - Specialty breakdown
  - Sentiment distribution
  - Top 5 unmet needs (by engagement)
  - Top 3 highlighted threads
"""

import os
from collections import Counter
from datetime import datetime

import requests
from dotenv import load_dotenv

from pipeline.synthesizer import ThreadSummary

load_dotenv()


def _sentiment_emoji(sentiment: str) -> str:
    return {
        "frustrated":     "😤",
        "uncertain":      "🤔",
        "seeking_advice": "🙋",
        "informational":  "📋",
        "debating":       "⚖️",
    }.get(sentiment, "💬")


def _build_blocks(summaries: list[ThreadSummary], stats: dict, date_str: str) -> list[dict]:
    # --- Specialty breakdown ---
    specialty_counts = Counter(s.community for s in summaries)
    specialty_line = "  ".join(
        f"*{community}* ({count})"
        for community, count in sorted(specialty_counts.items(), key=lambda x: -x[1])
    )

    # --- Sentiment distribution ---
    sentiment_counts = Counter(s.sentiment for s in summaries)
    total = len(summaries)
    sentiment_line = "  ".join(
        f"{_sentiment_emoji(k)} {k} {round(v/total*100)}%"
        for k, v in sentiment_counts.most_common()
    )

    # --- Top 5 unmet needs (highest comment_count, skip "None identified") ---
    top_needs = [
        s for s in sorted(summaries, key=lambda x: x.comment_count, reverse=True)
        if s.unmet_need.lower() not in ("none identified", "none", "n/a", "")
    ][:5]
    needs_lines = "\n".join(f"• {s.unmet_need}" for s in top_needs)

    # --- Top 3 highlighted threads ---
    top_threads = sorted(summaries, key=lambda x: x.comment_count, reverse=True)[:3]

    blocks = [
        # Header
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🏥 med-insights — {date_str}"}
        },
        {"type": "divider"},

        # Stats
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{len(summaries)} threads synthesized* "
                    f"from {stats.get('raw', '—')} scraped "
                    f"→ {stats.get('after_prefilter', '—')} pre-filtered "
                    f"→ {stats.get('after_llm_filter', '—')} passed Haiku\n\n"
                    f"{specialty_line}"
                )
            }
        },

        # Sentiment
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Sentiment*\n{sentiment_line}"}
        },
        {"type": "divider"},

        # Top unmet needs
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Top unmet needs*\n{needs_lines}"}
        },
        {"type": "divider"},

        # Highlighted threads
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Highlighted threads*"}
        },
    ]

    for t in top_threads:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{_sentiment_emoji(t.sentiment)} *<{t.url}|{t.headline}>*\n"
                    f"r/{t.community} · ↑{t.comment_count} comments\n"
                    f"_{t.unmet_need}_"
                )
            }
        })

    return blocks


def notify(summaries: list[ThreadSummary], stats: dict) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("  [slack] SLACK_WEBHOOK_URL not set — skipping notification")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    blocks = _build_blocks(summaries, stats, date_str)

    resp = requests.post(webhook_url, json={"blocks": blocks}, timeout=10)
    if resp.status_code == 200:
        print("  [slack] notification sent to #med-insights")
    else:
        print(f"  [slack] failed ({resp.status_code}): {resp.text}")
