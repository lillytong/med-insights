"""
Two-stage LLM relevance filter using Claude Haiku.

Stage 1 — title only (cheapest): classify as relevant / irrelevant / uncertain.
Stage 2 — title + body: only for posts where title was ambiguous.

Posts with obvious titles never pay for body tokens.
Both stages batch FILTER_BATCH_SIZE posts per API call.
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

A post is RELEVANT if its title suggests a practicing physician's:
- Clinical challenge or diagnostic uncertainty
- Workflow frustration or EHR/administrative pain point
- Unmet need in patient care or treatment
- Clinical debate where physicians lack clear guidance

A post is IRRELEVANT if the title suggests:
- Medical student exam or application content (USMLE, match, rank lists)
- Lifestyle, social, or entertainment content
- Humor or memes
- Patient-authored questions
- Compensation or career discussions with no clinical angle

A post is UNCERTAIN if the title alone is not enough to decide."""


def _build_title_prompt(posts: list[UnifiedPost]) -> str:
    entries = [
        f"[{i}] r/{p.community} | {p.title}"
        for i, p in enumerate(posts, 1)
    ]
    return (
        "\n".join(entries)
        + '\n\nReply with a JSON array only — one entry per post:\n'
        + '[{"id": 1, "decision": "relevant|irrelevant|uncertain"}, ...]'
    )


def _build_body_prompt(posts: list[UnifiedPost]) -> str:
    entries = []
    for i, p in enumerate(posts, 1):
        body_preview = p.body[:300].replace("\n", " ") if p.body else "(no body)"
        entries.append(f"[{i}] r/{p.community}\nTitle: {p.title}\nBody: {body_preview}")
    return (
        "\n\n".join(entries)
        + '\n\nReply with a JSON array only — one entry per post:\n'
        + '[{"id": 1, "relevant": true, "reason": "brief reason"}, ...]'
    )


def _parse_decisions(text: str, count: int) -> list[dict]:
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return [{"id": i + 1, "decision": "uncertain"} for i in range(count)]


def _parse_relevance(text: str, count: int) -> list[dict]:
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        # On parse failure default to keeping all
        return [{"id": i + 1, "relevant": True, "reason": "parse error — kept"} for i in range(count)]


def _run_batch(posts: list[UnifiedPost], prompt: str, parser, default_keep: bool) -> dict[str, dict]:
    """Run one batched Haiku call and return a map of post_id → decision dict."""
    batches = [posts[i:i + config.FILTER_BATCH_SIZE] for i in range(0, len(posts), config.FILTER_BATCH_SIZE)]
    results = {}

    for idx, batch in enumerate(batches):
        response = _client.messages.create(
            model=config.HAIKU_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt(batch)}],
        )
        decisions = parser(response.content[0].text, len(batch))
        decision_map = {d["id"]: d for d in decisions}

        for i, post in enumerate(batch, 1):
            results[post.post_id] = decision_map.get(i, {})

    return results


def llm_filter(posts: list[UnifiedPost]) -> tuple[list[UnifiedPost], list[dict]]:
    kept, dropped = [], []

    # --- Stage 1: title only ---
    print(f"  [haiku s1] classifying {len(posts)} titles...")
    batches = [posts[i:i + config.FILTER_BATCH_SIZE] for i in range(0, len(posts), config.FILTER_BATCH_SIZE)]

    relevant_posts, uncertain_posts = [], []

    for idx, batch in enumerate(batches):
        response = _client.messages.create(
            model=config.HAIKU_MODEL,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_title_prompt(batch)}],
        )
        decisions = _parse_decisions(response.content[0].text, len(batch))
        decision_map = {d["id"]: d for d in decisions}

        for i, post in enumerate(batch, 1):
            d = decision_map.get(i, {"decision": "uncertain"})
            decision = d.get("decision", "uncertain")

            if decision == "relevant":
                relevant_posts.append(post)
            elif decision == "irrelevant":
                dropped.append({"post_id": post.post_id, "title": post.title, "reason": "irrelevant title (stage 1)"})
            else:
                uncertain_posts.append(post)

    print(f"    → {len(relevant_posts)} relevant, {len(uncertain_posts)} uncertain, {len(dropped)} dropped")

    # --- Stage 2: title + body for uncertain posts only ---
    if uncertain_posts:
        print(f"  [haiku s2] resolving {len(uncertain_posts)} uncertain posts with body...")
        batches2 = [uncertain_posts[i:i + config.FILTER_BATCH_SIZE] for i in range(0, len(uncertain_posts), config.FILTER_BATCH_SIZE)]

        for idx, batch in enumerate(batches2):
            response = _client.messages.create(
                model=config.HAIKU_MODEL,
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _build_body_prompt(batch)}],
            )
            decisions = _parse_relevance(response.content[0].text, len(batch))
            decision_map = {d["id"]: d for d in decisions}

            for i, post in enumerate(batch, 1):
                d = decision_map.get(i, {"relevant": True, "reason": "missing — kept"})
                if d.get("relevant", True):
                    relevant_posts.append(post)
                else:
                    dropped.append({"post_id": post.post_id, "title": post.title, "reason": d.get("reason", "")})

    kept = relevant_posts
    return kept, dropped
