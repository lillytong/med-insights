"""
Embedding step — runs after synthesis.

Embeds each ThreadSummary using Voyage AI (voyage-3-lite, 512 dims).
Text input: headline + clinical_problem + unmet_need concatenated.
Embeddings are stored directly on the ThreadSummary object for inclusion in JSON output.
"""

import os

import voyageai
from dotenv import load_dotenv

import config
from pipeline.synthesizer import ThreadSummary

load_dotenv()

_client = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))


def embed_summaries(summaries: list[ThreadSummary]) -> list[ThreadSummary]:
    if not summaries:
        return summaries

    texts = [
        f"{s.headline}. {s.clinical_problem} {s.unmet_need}"
        for s in summaries
    ]

    all_embeddings = []
    for i in range(0, len(texts), config.EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + config.EMBEDDING_BATCH_SIZE]
        result = _client.embed(batch, model=config.EMBEDDING_MODEL, input_type="document")
        all_embeddings.extend(result.embeddings)

    for summary, embedding in zip(summaries, all_embeddings):
        summary.embedding = embedding

    return summaries
