"""
LLM-based relevance filter using Claude Haiku.
Sends FILTER_BATCH_SIZE posts per API call to minimize round trips.
On any parse failure the batch defaults to kept — err on the side of inclusion.
"""

import json
import os

import anthropic
from dotenv import load_dotenv

import config
from pipeline.harmonizer import UnifiedPost

load_dotenv()

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

_SYSTEM = """\
You filter Reddit posts from medical professional communities.

Mark a post as relevant ONLY if it clearly represents:
- A practicing physician's clinical challenge or diagnostic uncertainty
- A physician workflow frustration or EHR/administrative pain point
- An unmet need in patient care or treatment
- A clinical debate where physicians lack clear guidance

Mark as NOT relevant if the post is:
- Medical student exam or application content (USMLE, match, rank lists)
- General career advice or specialty selection
- Humor, memes, or social posts without clinical substance
- Patient-authored questions
- Compensation or salary discussions with no clinical angle
- Entertainment or media references"""


def _build_prompt(posts: list[UnifiedPost]) -> str:
    entries = []
    for i, post in enumerate(posts, 1):
        body_preview = (post.body[:300].replace("\n", " ")) if post.body else "(no body)"
        entries.append(f"[{i}] r/{post.community}\nTitle: {post.title}\nBody: {body_preview}")

    return (
        "\n\n".join(entries)
        + '\n\nReply with a JSON array only — one entry per post:\n'
        + '[{"id": 1, "relevant": true, "reason": "brief reason"}, ...]'
    )


def _parse(text: str, count: int) -> list[dict]:
    try:
        text = text.strip()
        if text.startswith("```"):
            # Strip markdown code fences
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        # Default to keeping all posts in this batch on parse failure
        return [{"id": i + 1, "relevant": True, "reason": "parse error — kept by default"} for i in range(count)]


def llm_filter(posts: list[UnifiedPost]) -> tuple[list[UnifiedPost], list[dict]]:
    kept, dropped = [], []

    batches = [posts[i:i + config.FILTER_BATCH_SIZE] for i in range(0, len(posts), config.FILTER_BATCH_SIZE)]

    for idx, batch in enumerate(batches):
        print(f"  [haiku] batch {idx + 1}/{len(batches)} ({len(batch)} posts)...")

        response = _client.messages.create(
            model=config.HAIKU_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_prompt(batch)}],
        )

        decisions = _parse(response.content[0].text, len(batch))
        decision_map = {d["id"]: d for d in decisions}

        for i, post in enumerate(batch, 1):
            d = decision_map.get(i, {"relevant": True, "reason": "missing decision — kept"})
            if d.get("relevant", True):
                kept.append(post)
            else:
                dropped.append({
                    "post_id": post.post_id,
                    "title": post.title,
                    "reason": d.get("reason", ""),
                })

    return kept, dropped
