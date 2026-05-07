"""
ChromaDB vector store.

Persists to data/chroma/ on disk — survives restarts, accumulates across runs.

Each record stored has:
  - id:         post_id (deduplication key)
  - embedding:  384-dim bge-small vector
  - document:   headline + clinical_problem + unmet_need (the text that was embedded)
  - metadata:   community, sentiment, specialty_tags, comment_count, timestamp, url

Query example:
    results = query("prior auth blocking biologics", n_results=5)
    results = query("airway management", n_results=5, where={"community": "anesthesiology"})
"""

import chromadb
import config
from pipeline.synthesizer import ThreadSummary


def _get_collection():
    client = chromadb.PersistentClient(path=config.CHROMA_DIR)
    return client.get_or_create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},   # cosine similarity
    )


def upsert_summaries(summaries: list[ThreadSummary]) -> int:
    """Insert or update summaries in the vector store. Returns count upserted."""
    if not summaries:
        return 0

    collection = _get_collection()

    ids, embeddings, documents, metadatas = [], [], [], []

    for s in summaries:
        if not s.embedding:
            continue

        ids.append(s.post_id)
        embeddings.append(s.embedding)
        documents.append(f"{s.headline}. {s.clinical_problem} {s.unmet_need}")
        metadatas.append({
            "community":     s.community,
            "sentiment":     s.sentiment,
            "specialty_tags": ", ".join(s.specialty_tags),   # Chroma metadata must be str/int/float
            "comment_count": s.comment_count,
            "timestamp":     s.timestamp,
            "url":           s.url,
            "headline":      s.headline,
            "unmet_need":    s.unmet_need,
        })

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    return len(ids)


def query(text: str, n_results: int = 10, where: dict = None) -> list[dict]:
    """
    Semantic search over stored insights.

    Args:
        text:      Natural language query
        n_results: How many results to return
        where:     Optional metadata filter, e.g. {"community": "anesthesiology"}

    Returns list of dicts with keys: id, document, metadata, distance
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(config.EMBEDDING_MODEL)
    query_embedding = model.encode([text], normalize_embeddings=True)[0].tolist()

    collection = _get_collection()

    kwargs = {"query_embeddings": [query_embedding], "n_results": n_results}
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    out = []
    for i in range(len(results["ids"][0])):
        out.append({
            "id":       results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })

    return out


def count() -> int:
    """Total number of insights stored."""
    return _get_collection().count()


def restore_from_checkpoints() -> int:
    """
    Rebuild ChromaDB from all synthesis checkpoints in data/synthesis/.
    Used at the start of CI runs where ChromaDB doesn't persist between jobs.
    Skips if ChromaDB already has records (nothing to restore).
    Returns number of records upserted (0 if already populated).
    """
    if count() > 0:
        return 0

    import json
    from pathlib import Path
    from pipeline.synthesizer import ThreadSummary
    from pipeline.embedder import embed_summaries

    synthesis_dir = Path(config.SYNTHESIS_DIR)
    if not synthesis_dir.exists():
        return 0

    all_summaries = []
    for checkpoint in sorted(synthesis_dir.glob("*.jsonl")):
        for line in checkpoint.read_text().splitlines():
            if line.strip():
                all_summaries.append(ThreadSummary(**json.loads(line)))

    if not all_summaries:
        return 0

    print(f"  [chroma] restoring {len(all_summaries)} summaries from checkpoints...")
    all_summaries = embed_summaries(all_summaries)
    n = upsert_summaries(all_summaries)

    # Restore cluster assignments if available
    assignments_path = Path("data") / "cluster_assignments.json"
    if assignments_path.exists():
        print(f"  [chroma] restoring cluster assignments...")
        assignments = json.loads(assignments_path.read_text())
        collection = _get_collection()
        data = collection.get(include=["metadatas"])

        update_ids, update_metadatas = [], []
        for pid, meta in zip(data["ids"], data["metadatas"]):
            if pid in assignments:
                new_meta = dict(meta)
                new_meta["cluster_id"] = assignments[pid]["cluster_id"]
                new_meta["umap_x"]     = assignments[pid]["umap_x"]
                new_meta["umap_y"]     = assignments[pid]["umap_y"]
                update_ids.append(pid)
                update_metadatas.append(new_meta)

        batch = 500
        for start in range(0, len(update_ids), batch):
            collection.update(
                ids=update_ids[start:start + batch],
                metadatas=update_metadatas[start:start + batch],
            )
        print(f"  [chroma] restored cluster assignments for {len(update_ids)} posts")

    return n
