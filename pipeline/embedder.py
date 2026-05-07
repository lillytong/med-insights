"""
Embedding step — runs after synthesis.

Embeds each ThreadSummary using BAAI/bge-small-en-v1.5 via sentence-transformers.
Runs locally, no API key required. Model (~130MB) is downloaded on first use
and cached at ~/.cache/huggingface/.

Text input: headline + clinical_problem + unmet_need concatenated.
Embeddings are stored directly on the ThreadSummary object.
"""

from sentence_transformers import SentenceTransformer

import config
from pipeline.synthesizer import ThreadSummary

_model = SentenceTransformer(config.EMBEDDING_MODEL)


def embed_summaries(summaries: list[ThreadSummary]) -> list[ThreadSummary]:
    if not summaries:
        return summaries

    texts = [
        f"{s.headline}. {s.clinical_problem} {s.unmet_need}"
        for s in summaries
    ]

    all_embeddings = _model.encode(
        texts,
        batch_size=config.EMBEDDING_BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    for summary, embedding in zip(summaries, all_embeddings):
        summary.embedding = embedding.tolist()

    return summaries
