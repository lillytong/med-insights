"""
Per-thread synthesis using Claude Sonnet.
Runs concurrently (bounded by SYNTHESIS_CONCURRENCY) for throughput.
Uses tool_use to guarantee structured JSON output — no fragile parsing.
"""

import asyncio
import json
import os
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

import config
from pipeline.harmonizer import UnifiedPost

load_dotenv()

_client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Tool schema enforces the exact shape we want back from Sonnet
_SUMMARY_TOOL = {
    "name": "record_thread_summary",
    "description": "Record a structured clinical insight summary from a physician community thread.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "One sentence capturing the core clinical problem or pain point",
            },
            "clinical_problem": {
                "type": "string",
                "description": "Clear description of the clinical challenge or physician frustration",
            },
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 key insights drawn from the thread discussion",
            },
            "unmet_need": {
                "type": "string",
                "description": "What tool, guideline, or solution physicians are lacking. 'None identified' if not applicable.",
            },
            "specialty_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Medical specialties relevant to this thread (e.g. ['emergency medicine', 'cardiology'])",
            },
            "sentiment": {
                "type": "string",
                "enum": ["frustrated", "uncertain", "seeking_advice", "informational", "debating"],
                "description": "Dominant tone of the thread",
            },
        },
        "required": [
            "headline", "clinical_problem", "key_findings",
            "unmet_need", "specialty_tags", "sentiment",
        ],
    },
}


@dataclass
class ThreadSummary:
    post_id: str
    community: str
    url: str
    comment_count: int
    timestamp: str
    headline: str
    clinical_problem: str
    key_findings: list[str]
    unmet_need: str
    specialty_tags: list[str]
    sentiment: str
    embedding: list[float] = field(default_factory=list)


def _build_thread_text(post: UnifiedPost) -> str:
    lines = [
        f"Subreddit: r/{post.community}",
        f"Title: {post.title}",
        f"Post: {post.body[:500].replace(chr(10), ' ') if post.body else '(no body)'}",
        "",
        "Top comments:",
    ]
    for i, comment in enumerate(post.top_comments, 1):
        words = comment["body"].split()
        truncated = " ".join(words[:config.MAX_COMMENT_WORDS])
        if len(words) > config.MAX_COMMENT_WORDS:
            truncated += "..."
        lines.append(f"{i}. {truncated}")
    return "\n".join(lines)


async def _synthesize_one(post: UnifiedPost, semaphore: asyncio.Semaphore) -> Optional[ThreadSummary]:
    async with semaphore:
        max_retries = 4
        for attempt in range(max_retries):
            try:
                response = await _client.messages.create(
                    model=config.SONNET_MODEL,
                    max_tokens=900,
                    system=(
                        "You are a medical insights analyst. Synthesize Reddit threads from physician "
                        "communities into structured clinical insights. Focus on recurring pain points, "
                        "unmet needs, and clinical challenges that practicing physicians face."
                    ),
                    messages=[{
                        "role": "user",
                        "content": f"Synthesize this physician community thread:\n\n{_build_thread_text(post)}",
                    }],
                    tools=[_SUMMARY_TOOL],
                    tool_choice={"type": "tool", "name": "record_thread_summary"},
                )

                tool_block = next(b for b in response.content if b.type == "tool_use")
                return ThreadSummary(
                    post_id=post.post_id,
                    community=post.community,
                    url=post.url,
                    comment_count=post.comment_count,
                    timestamp=post.timestamp,
                    **tool_block.input,
                )
            except anthropic.RateLimitError:
                if attempt == max_retries - 1:
                    print(f"\n  [synthesizer] rate limit, giving up on {post.post_id}")
                    return None
                wait = 2 ** attempt + random.random()
                await asyncio.sleep(wait)
            except Exception as e:
                print(f"\n  [synthesizer] error on {post.post_id}: {e}")
                return None


def _checkpoint_path(date_str: str) -> Path:
    p = Path(config.SYNTHESIS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{date_str}.jsonl"


def _load_checkpoint(path: Path) -> tuple[dict[str, ThreadSummary], set[str]]:
    """Returns (summaries_by_id, done_ids) from an existing checkpoint file."""
    summaries: dict[str, ThreadSummary] = {}
    if not path.exists():
        return summaries, set()
    for line in path.read_text().splitlines():
        if not line:
            continue
        d = json.loads(line)
        summaries[d["post_id"]] = ThreadSummary(**d)
    return summaries, set(summaries.keys())


async def synthesize_all(posts: list[UnifiedPost]) -> list[ThreadSummary]:
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    checkpoint = _checkpoint_path(date_str)
    cached, done_ids = _load_checkpoint(checkpoint)

    pending = [p for p in posts if p.post_id not in done_ids]
    if cached:
        print(f"  [checkpoint] {len(cached)} already done, {len(pending)} remaining")

    semaphore = asyncio.Semaphore(config.SYNTHESIS_CONCURRENCY)
    tasks = [_synthesize_one(post, semaphore) for post in pending]
    results = list(cached.values())

    with checkpoint.open("a") as f:
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            if result:
                results.append(result)
                f.write(json.dumps(result.__dict__) + "\n")
                f.flush()
            print(f"  [sonnet] {i}/{len(tasks)} complete", end="\r")

    print()
    return results
