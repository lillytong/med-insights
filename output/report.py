import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from pipeline.synthesizer import ThreadSummary


def save_json(summaries: list[ThreadSummary], output_dir: str) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    Path(output_dir, date_str).mkdir(parents=True, exist_ok=True)
    path = f"{output_dir}/{date_str}/insights_{date_str}.json"
    records = [
        {k: v for k, v in asdict(s).items() if k != "embedding"}
        for s in summaries
    ]
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    return path


def save_markdown(summaries: list[ThreadSummary], output_dir: str, stats: dict) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    Path(output_dir, date_str).mkdir(parents=True, exist_ok=True)
    path = f"{output_dir}/{date_str}/report_{date_str}.md"

    # Group by community, sort each group by comment_count desc
    by_community: dict[str, list[ThreadSummary]] = {}
    for s in summaries:
        by_community.setdefault(s.community, []).append(s)
    for threads in by_community.values():
        threads.sort(key=lambda x: x.comment_count, reverse=True)

    lines = [
        f"# Medical Insights Report — {date_str}",
        "",
        "## Pipeline stats",
        f"- Raw posts scraped: **{stats.get('raw', 0)}**",
        f"- After rule-based pre-filter: **{stats.get('after_prefilter', 0)}**",
        f"- After Haiku filter: **{stats.get('after_llm_filter', 0)}**",
        f"- Threads synthesized: **{len(summaries)}**",
        "",
        "---",
        "",
    ]

    for community, threads in sorted(by_community.items()):
        lines += [f"## r/{community}  ({len(threads)} threads)", ""]
        for t in threads:
            lines += [
                f"### {t.headline}",
                f"*{t.sentiment} · {t.comment_count} comments · [view thread]({t.url})*",
                "",
                f"**Problem:** {t.clinical_problem}",
                "",
                "**Key findings:**",
            ]
            for finding in t.key_findings:
                lines.append(f"- {finding}")
            lines += [
                "",
                f"**Unmet need:** {t.unmet_need}",
                f"**Specialties:** {', '.join(t.specialty_tags)}",
                "",
                "---",
                "",
            ]

    with open(path, "w") as f:
        f.write("\n".join(lines))

    return path
